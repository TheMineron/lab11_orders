import uuid

from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
	class Meta:
		model = OrderItem
		fields = ['id', 'product_id', 'product_name', 'quantity',
				  'unit_price', 'total_price']
		read_only_fields = ['id', 'total_price']


class OrderSerializer(serializers.ModelSerializer):
	items = OrderItemSerializer(many=True, required=False)

	class Meta:
		model = Order
		fields = [
			'id', 'order_number', 'customer_id', 'customer_email',
			'customer_name', 'status', 'payment_status', 'delivering_address',
			'delivering_city', 'delivering_country', 'subtotal', 'delivering_cost',
			'total_amount', 'created_at', 'updated_at', 'paid_at', 'delivered_at',
			'delivered_at', 'notes', 'items'
		]
		read_only_fields = [
			'id', 'order_number', 'created_at', 'updated_at',
			'paid_at', 'delivered_at', 'delivered_at'
		]

	def create(self, validated_data):
		items_data = validated_data.pop('items', [])

		validated_data['order_number'] = f"ORD-{uuid.uuid4().hex[:8].upper()}"

		items_total = sum(item['quantity'] * item['unit_price'] for item in items_data)
		validated_data['subtotal'] = items_total
		validated_data['total_amount'] = items_total + validated_data.get('delivering_cost', 0)

		order = Order.objects.create(**validated_data)

		for item_data in items_data:
			item_data['total_price'] = item_data['quantity'] * item_data['unit_price']
			OrderItem.objects.create(order=order, **item_data)

		return order

	def update(self, instance, validated_data):
		items_data = validated_data.pop('items', None)

		for attr, value in validated_data.items():
			setattr(instance, attr, value)

		if items_data is not None:
			instance.items.all().delete()

			for item_data in items_data:
				item_data['total_price'] = item_data['quantity'] * item_data['unit_price']
				OrderItem.objects.create(order=instance, **item_data)

		instance.save()
		return instance


class OrderStatusUpdateSerializer(serializers.Serializer):
	status = serializers.ChoiceField(choices=Order.ORDER_STATUS)
	notes = serializers.CharField(required=False, allow_blank=True)
