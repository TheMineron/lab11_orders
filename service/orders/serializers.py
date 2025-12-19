from django.utils import timezone
from rest_framework import serializers
from django.core.exceptions import ValidationError
import uuid

from .models import Order, OrderItem
from .validators import validate_order_editability, validate_order_payment_status_transition


class OrderItemSerializer(serializers.ModelSerializer):
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product_id', 'product_name', 'quantity',
                  'unit_price', 'total_price']
        read_only_fields = ['id', 'total_price']

    def get_total_price(self, obj):
        return obj.quantity * obj.unit_price

    def validate(self, data):
        if data['quantity'] <= 0:
            raise serializers.ValidationError({
                "quantity": "Quantity must be greater than 0"
            })
        if data['unit_price'] < 0:
            raise serializers.ValidationError({
                "unit_price": "Unit price cannot be negative"
            })
        return data

    def create(self, validated_data):
        order = self.context['order']
        if not self._can_update_items(order):
            raise ValidationError('Cannot add items to order in current status')
        return super().create({**validated_data, 'order': order})

    def update(self, instance, validated_data):
        if not self._can_update_items(instance.order):
            raise ValidationError('Cannot update items in order in current status')
        return super().update(instance, validated_data)

    def _can_update_items(self, order):
        return order.status in ['pending']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, required=False)
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer_id', 'customer_email',
            'customer_name', 'status', 'payment_status', 'delivering_address',
            'delivering_city', 'delivering_country', 'subtotal', 'delivering_cost',
            'created_at', 'updated_at', 'paid_at', 'delivered_at',
            'cancelled_at', 'refunded_at', 'notes', 'items', 'total_amount'
        ]
        read_only_fields = [
            'id', 'order_number', 'created_at', 'updated_at',
            'paid_at', 'delivered_at', 'cancelled_at', 'refunded_at',
            'subtotal', 'total_amount', 'payment_status', 'status'
        ]

    def get_total_amount(self, obj):
        return obj.subtotal + obj.delivering_cost

    def validate(self, data):
        instance = self.instance

        if instance:
            try:
                validate_order_editability(
                    instance,
                    fields_to_update=list(data.keys())
                )
            except ValidationError as e:
                raise serializers.ValidationError(str(e))

        if 'delivering_cost' in data and data['delivering_cost'] < 0:
            raise serializers.ValidationError({
                "delivering_cost": "Delivery cost cannot be negative"
            })

        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])

        if not validated_data.get('order_number'):
            validated_data['order_number'] = f"ORD-{uuid.uuid4().hex[:8].upper()}"

        order = Order.objects.create(**validated_data)

        if items_data:
            order_items = []
            for item_data in items_data:
                order_item = OrderItem(order=order, **item_data)
                order_items.append(order_item)

            OrderItem.objects.bulk_create(order_items)

        self._recalculate_subtotal(order)

        return order

    def update(self, instance: Order, validated_data):
        items_data = validated_data.pop('items', None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            if items_data:
                order_items = []
                for item_data in items_data:
                    order_item = OrderItem(order=instance, **item_data)
                    order_items.append(order_item)
                OrderItem.objects.bulk_create(order_items)

            self._recalculate_subtotal(instance)

        return instance

    def _recalculate_subtotal(self, order):
        from django.db.models import Sum, F
        result = order.items.aggregate(
            subtotal=Sum(F('quantity') * F('unit_price'), default=0)
        )
        order.subtotal = result['subtotal']
        order.save(update_fields=['subtotal', 'updated_at'])


class OrderPaymentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['payment_status']

    def validate_payment_status(self, value):
        order = self.instance
        current_status = order.payment_status

        try:
            validate_order_payment_status_transition(
                current_status,
                value
            )
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

        return value

    def update(self, instance, validated_data):
        if validated_data.get('payment_status') == 'paid' and not instance.paid_at:
            instance.paid_at = timezone.now()

        instance.payment_status = validated_data['payment_status']
        instance.save()
        return instance
