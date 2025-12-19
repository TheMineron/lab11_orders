from django.core.exceptions import ValidationError
from django.utils import timezone


VALID_TRANSITIONS = {
	'pending': ['processing', 'cancelled'],
	'processing': ['delivered', 'cancelled'],
	'delivered': ['refunded'],
	'cancelled': [],
	'refunded': [],
}

ALLOWED_STATUSES = VALID_TRANSITIONS.keys()

PAYMENT_STATUS_RULES = {
	'cancelled': {
		'paid': 'refunded',
		'pending': 'pending',
		'failed': 'failed',
		'refunded': 'refunded',
	},
	'refunded': {
		'paid': 'refunded',
		'pending': 'refunded',
		'failed': 'refunded',
		'refunded': 'refunded',
	},
	'delivered': {
		'paid': 'paid',
		'pending': 'pending',
		'failed': 'failed',
		'refunded': 'refunded',
	}
}

VALID_PAYMENT_TRANSITIONS = {
	'pending': ['paid', 'failed'],
	'paid': ['refunded'],
	'failed': ['pending', 'paid'],
	'refunded': []
}


def validate_order_status_transition(old_status, new_status, order=None):
	if new_status not in VALID_TRANSITIONS.get(old_status, []):
		raise ValidationError(
			f'Invalid status transition from {old_status} to {new_status}'
		)

	if new_status == 'delivered' and order:
		if order.payment_status != 'paid':
			raise ValidationError('Cannot deliver unpaid order')

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


def update_order_status(order, new_status, notes=None):
	validate_order_status_transition(order.status, new_status, order)

	order.status = new_status

	if new_status in PAYMENT_STATUS_RULES:
		payment_rule = PAYMENT_STATUS_RULES[new_status]
		new_payment_status = payment_rule.get(order.payment_status, order.payment_status)
		order.payment_status = new_payment_status

	if new_status == 'cancelled' and not order.cancelled_at:
		order.cancelled_at = timezone.now()
	elif new_status == 'refunded' and not order.refunded_at:
		order.refunded_at = timezone.now()
	elif new_status == 'delivered' and not order.delivered_at:
		order.delivered_at = timezone.now()

	if notes is not None:
		current_notes = order.notes or ''
		order.notes = f"{current_notes}\n{notes}".strip()

	order.save()
	return order


def validate_order_payment_status_transition(old_status, new_status):
	if new_status not in VALID_PAYMENT_TRANSITIONS.get(old_status, []):
		raise ValidationError(
			f'Cannot change payment status from {old_status} to {new_status}'
		)

	return True
