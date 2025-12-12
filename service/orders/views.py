from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderStatusUpdateSerializer


class OrderViewSet(viewsets.ModelViewSet):
	queryset = Order.objects.all()
	serializer_class = OrderSerializer
	permission_classes = [IsAuthenticatedOrReadOnly]
	filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
	filterset_fields = ['status', 'payment_status', 'customer_id', 'shipping_country']
	search_fields = ['order_number', 'customer_name', 'customer_email']
	ordering_fields = ['created_at', 'total_amount', 'updated_at']
	ordering = ['-created_at']

	@action(detail=True, methods=['post'])
	def update_status(self, request, pk=None):
		order = self.get_object()
		serializer = OrderStatusUpdateSerializer(data=request.data)

		if serializer.is_valid():
			new_status = serializer.validated_data['status']

			valid_transitions = {
				'pending': ['processing', 'cancelled'],
				'processing': ['shipped', 'cancelled'],
				'shipped': ['delivered'],
				'delivered': ['refunded'],
				'cancelled': [],
				'refunded': [],
			}

			if new_status not in valid_transitions.get(order.status, []):
				return Response(
					{'error': f'Invalid status transition from {order.status} to {new_status}'},
					status=status.HTTP_400_BAD_REQUEST
				)

			order.status = new_status

			if new_status == 'paid':
				order.paid_at = timezone.now()
			elif new_status == 'shipped':
				order.shipped_at = timezone.now()
			elif new_status == 'delivered':
				order.delivered_at = timezone.now()

			order.save()

			return Response(OrderSerializer(order).data)

		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

	@action(detail=False, methods=['get'])
	def by_customer(self, request):
		customer_id = request.query_params.get('customer_id')

		if not customer_id:
			return Response(
				{'error': 'customer_id parameter is required'},
				status=status.HTTP_400_BAD_REQUEST
			)

		try:
			customer_id = int(customer_id)
		except ValueError:
			return Response(
				{'error': 'customer_id must be an integer'},
				status=status.HTTP_400_BAD_REQUEST
			)

		orders = Order.objects.filter(customer_id=customer_id)
		page = self.paginate_queryset(orders)

		if page is not None:
			serializer = self.get_serializer(page, many=True)
			return self.get_paginated_response(serializer.data)

		serializer = self.get_serializer(orders, many=True)
		return Response(serializer.data)

	@action(detail=True, methods=['get'])
	def items(self, request, pk=None):
		order = self.get_object()
		items = OrderItem.objects.filter(order=order)

		data = [{
			'product_id': item.product_id,
			'product_name': item.product_name,
			'quantity': item.quantity,
			'unit_price': str(item.unit_price),
			'total_price': str(item.total_price)
		} for item in items]

		return Response(data)
	