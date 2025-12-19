from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Order, OrderItem
from .serializers import (
	OrderSerializer,
	OrderStatusUpdateSerializer
)


class OrderViewSet(viewsets.ModelViewSet):
	queryset = Order.objects.all()
	serializer_class = OrderSerializer
	filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
	filterset_fields = ['status', 'payment_status', 'customer_id', 'delivering_country']
	search_fields = ['order_number', 'customer_name', 'customer_email']
	ordering_fields = ['created_at', 'total_amount', 'updated_at']
	ordering = ['-created_at']

	@action(detail=True, methods=['post'])
	def update_status(self, request, pk=None):
		order = self.get_object()
		serializer = OrderStatusUpdateSerializer(
			data=request.data,
			context={'request': request, 'view': self}
		)

		serializer.is_valid(raise_exception=True)
		order = serializer.update(order, serializer.validated_data)

		return Response(OrderSerializer(order).data)

	@action(detail=True, methods=['get'])
	def items(self, request, pk=None):
		order = self.get_object()
		items = OrderItem.objects.filter(order=order)
		data = [{
			'id': item.id,
			'product_id': item.product_id,
			'product_name': item.product_name,
			'quantity': item.quantity,
			'unit_price': str(item.unit_price),
			'total_price': str(item.total_price)
		} for item in items]

		return Response(data)

	@action(detail=True, methods=['post'])
	def cancel(self, request, pk=None):
		from .validators import validate_order_status_transition

		order = self.get_object()

		try:
			validate_order_status_transition(order.status, 'cancelled', order)
		except ValidationError as e:
			return Response(
				{'error': str(e)},
				status=status.HTTP_400_BAD_REQUEST
			)

		order.status = 'cancelled'
		order.cancelled_at = timezone.now()
		order.save()

		return Response(OrderSerializer(order).data)

	@action(detail=True, methods=['post'])
	def refund(self, request, pk=None):
		from .validators import validate_order_status_transition

		order = self.get_object()

		try:
			validate_order_status_transition(order.status, 'refunded', order)
		except ValidationError as e:
			return Response(
				{'error': str(e)},
				status=status.HTTP_400_BAD_REQUEST
			)

		order.status = 'refunded'
		order.payment_status = 'refunded'
		order.refunded_at = timezone.now()
		order.save()

		return Response(OrderSerializer(order).data)
