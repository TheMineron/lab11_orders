from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid

from .models import Order, OrderItem
from .validators import (
	validate_order_status_transition,
	validate_order_editability
)


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
			'subtotal', 'total_amount'
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

			if 'status' in data and data['status'] != instance.status:
				try:
					validate_order_status_transition(
						instance.status,
						data['status'],
						instance
					)
				except ValidationError as e:
					raise serializers.ValidationError({'status': str(e)})

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

		self._handle_status_changes(instance, validated_data)

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

	def _handle_status_changes(self, order, validated_data):
		if 'status' in validated_data:
			if validated_data['status'] == 'delivered' and not order.delivered_at:
				order.delivered_at = timezone.now()
			elif validated_data['status'] == 'cancelled' and not order.cancelled_at:
				order.cancelled_at = timezone.now()
			elif validated_data['status'] == 'refunded' and not order.refunded_at:
				order.refunded_at = timezone.now()

		if 'payment_status' in validated_data:
			if validated_data['payment_status'] == 'paid' and not order.paid_at:
				order.paid_at = timezone.now()


class OrderStatusUpdateSerializer(serializers.Serializer):
	status = serializers.ChoiceField(choices=Order.ORDER_STATUS)
	notes = serializers.CharField(required=False, allow_blank=True)

	def validate(self, data):
		request = self.context.get('request')
		view = self.context.get('view')

		if request and view:
			order = view.get_object()

			try:
				validate_order_status_transition(
					order.status,
					data['status'],
					order
				)
			except ValidationError as e:
				raise serializers.ValidationError({'status': str(e)})

		return data

	def update(self, instance, validated_data):
		instance.status = validated_data['status']

		if 'notes' in validated_data:
			instance.notes = validated_data['notes']

		if instance.status == 'delivered' and not instance.delivered_at:
			instance.delivered_at = timezone.now()
		elif instance.status == 'cancelled' and not instance.cancelled_at:
			instance.cancelled_at = timezone.now()
		elif instance.status == 'refunded' and not instance.refunded_at:
			instance.refunded_at = timezone.now()

		instance.save()
		return instance
