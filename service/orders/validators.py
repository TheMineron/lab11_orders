from django.core.exceptions import ValidationError

VALID_TRANSITIONS = {
	'pending': ['processing', 'cancelled'],
	'processing': ['delivered', 'cancelled'],
	'delivered': ['refunded'],
	'cancelled': [],
	'refunded': [],
}


def validate_order_status_transition(old_status, new_status, order=None):
	if new_status not in VALID_TRANSITIONS.get(old_status, []):
		raise ValidationError(
			f'Invalid status transition from {old_status} to {new_status}'
		)

	if new_status == 'delivered' and order:
		if order.payment_status != 'paid':
			raise ValidationError('Cannot deliver unpaid order')

	if new_status == 'cancelled' and order:
		if order.status == 'delivered':
			raise ValidationError('Cannot cancel delivered order')

	return True


def validate_order_editability(order, fields_to_update=None):
	non_editable_statuses = ['delivered', 'cancelled', 'refunded']

	if order.status in non_editable_statuses:
		raise ValidationError(
			f'Order cannot be edited in status: {order.status}'
		)

	if order.status == 'processing' and fields_to_update:
		restricted_fields = ['delivering_address', 'delivering_city', 'delivering_country']
		if any(field in fields_to_update for field in restricted_fields):
			raise ValidationError(
				'Cannot change delivery address when order is processing'
			)

	return True
