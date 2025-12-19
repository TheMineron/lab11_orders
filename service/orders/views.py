from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderPaymentStatusSerializer, OrderItemSerializer
from .validators import update_order_status  # Новая функция


class OrderViewSet(viewsets.ModelViewSet):
	queryset = Order.objects.all()
	serializer_class = OrderSerializer
	filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
	filterset_fields = ['status', 'payment_status', 'customer_id', 'delivering_country']
	search_fields = ['order_number', 'customer_name', 'customer_email']
	ordering_fields = ['created_at', 'total_amount', 'updated_at']
	ordering = ['-created_at']

	@action(detail=True, methods=['get'])
	def items(self, request, pk=None):
		order = self.get_object()
		items = OrderItem.objects.filter(order=order)
		serializer = OrderItemSerializer(items, many=True)
		return Response(serializer.data)

	@action(detail=True, methods=['patch'], url_path='payment-status')
	def update_payment_status(self, request, pk=None):
		order = self.get_object()
		serializer = OrderPaymentStatusSerializer(
			order,
			data=request.data,
			partial=True
		)

		serializer.is_valid(raise_exception=True)
		serializer.save()

		return Response(OrderSerializer(order).data)

	@action(detail=True, methods=['patch'], url_path='status')
	def update_status(self, request, pk=None):
		order = self.get_object()
		new_status = request.data.get('status')
		notes = request.data.get('notes')

		try:
			order = update_order_status(
				order=order,
				new_status=new_status,
				notes=notes
			)
		except ValidationError as e:
			return Response(
				{'error': str(e)},
				status=status.HTTP_400_BAD_REQUEST
			)

		return Response(OrderSerializer(order).data)
