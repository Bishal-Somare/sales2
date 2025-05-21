# notifications/views.py
import json
import decimal
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.mail import send_mail, get_connection, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt # Only for AJAX if not handling CSRF via JS
from django.db.models import Sum, F, Q, Exists, OuterRef, Value, DecimalField
from django.db.models.functions import Coalesce


# Assuming your models are in these locations
from accounts.models import Customer
from transactions.models import Sale # Required to calculate due amounts

# Helper function to calculate total due for a customer
def _calculate_customer_total_due(customer):
    total_due = decimal.Decimal('0.00')
    # The Sale model's amount_to_pay property correctly calculates individual sale dues.
    # We sum this property for all sales of the customer.
    for sale in customer.sale_set.all(): # sale_set is the default related_name
        total_due += sale.amount_to_pay
    return total_due

@require_GET
def get_customer_due_amount_ajax(request, customer_id):
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request type.'}, status=400)
    try:
        customer = get_object_or_404(Customer, pk=customer_id)
        total_due = _calculate_customer_total_due(customer)
        return JsonResponse({
            'customer_name': customer.get_full_name(),
            'due_amount': str(total_due.quantize(decimal.Decimal('0.01')))
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def send_due_reminder_page(request):
    if request.method == 'GET':
        customers = Customer.objects.all().order_by('first_name', 'last_name')
        context = {
            'customers': customers,
        }
        return render(request, 'notifications/send_due_reminders.html', context)

    elif request.method == 'POST':
        if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Invalid request type for POST.'}, status=400)

        try:
            data = json.loads(request.body)
            action = data.get('action')

            if action == 'send_single':
                customer_id = data.get('customer_id')
                if not customer_id:
                    return JsonResponse({'error': 'Customer ID is required.'}, status=400)
                
                customer = get_object_or_404(Customer, pk=customer_id)
                amount_due = _calculate_customer_total_due(customer)

                if amount_due <= 0:
                    return JsonResponse({'message': f'{customer.get_full_name()} has no outstanding balance.', 'status': 'info'})

                if not customer.email:
                    return JsonResponse({'error': f'{customer.get_full_name()} does not have an email address configured.'}, status=400)

                email_context = {
                    'customer_name': customer.get_full_name(),
                    'amount_due': amount_due.quantize(decimal.Decimal('0.01'))
                }
                subject = render_to_string('notifications/email/due_reminder_subject.txt', email_context).strip()
                html_body = render_to_string('notifications/email/due_reminder_body.html', email_context)
                
                try:
                    send_mail(
                        subject,
                        '', # Plain text part, html_message will be used
                        settings.EMAIL_HOST_USER,
                        [customer.email],
                        html_message=html_body,
                        fail_silently=False,
                    )
                    return JsonResponse({'message': f'Email sent successfully to {customer.get_full_name()}.', 'status': 'success'})
                except Exception as e:
                    return JsonResponse({'error': f'Failed to send email to {customer.get_full_name()}: {str(e)}'}, status=500)

            elif action == 'send_all':
                # Find customers with any outstanding balance
                # A customer has debt if any of their sales has amount_to_pay > 0
                customers_with_any_debt = Customer.objects.annotate(
                    has_debt=Exists(Sale.objects.filter(customer=OuterRef('pk'), grand_total__gt=F('amount_paid')))
                ).filter(has_debt=True).distinct()
                
                if not customers_with_any_debt.exists():
                     return JsonResponse({'message': 'No customers found with outstanding payments.', 'status': 'info'})

                email_messages = []
                successfully_queued_customers = []
                failed_customers = []

                for customer in customers_with_any_debt:
                    amount_due = _calculate_customer_total_due(customer)
                    if amount_due > 0 and customer.email:
                        email_context = {
                            'customer_name': customer.get_full_name(),
                            'amount_due': amount_due.quantize(decimal.Decimal('0.01'))
                        }
                        subject = render_to_string('notifications/email/due_reminder_subject.txt', email_context).strip()
                        html_body = render_to_string('notifications/email/due_reminder_body.html', email_context)
                        
                        msg = EmailMessage(
                            subject,
                            html_body, # Body is HTML
                            settings.EMAIL_HOST_USER,
                            [customer.email]
                        )
                        msg.content_subtype = "html"  # Main content is now HTML
                        email_messages.append(msg)
                        successfully_queued_customers.append(customer.get_full_name())
                    elif amount_due > 0 and not customer.email:
                        failed_customers.append(f"{customer.get_full_name()} (no email)")


                if not email_messages:
                    if failed_customers:
                         return JsonResponse({
                            'message': f'No emails could be prepared. Issues: {", ".join(failed_customers)}', 
                            'status': 'warning'
                        })
                    return JsonResponse({'message': 'No customers with valid emails and outstanding payments found.', 'status': 'info'})

                try:
                    connection = get_connection(fail_silently=False) # Use default backend
                    connection.open()
                    num_sent = connection.send_messages(email_messages)
                    connection.close()
                    
                    response_message = f'{num_sent} emails sent successfully to: {", ".join(successfully_queued_customers)}.'
                    if failed_customers:
                        response_message += f' Could not send to: {", ".join(failed_customers)}.'
                    
                    return JsonResponse({'message': response_message, 'status': 'success', 'sent_count': num_sent})
                except Exception as e:
                    return JsonResponse({'error': f'Error during batch email sending: {str(e)}'}, status=500)
            
            else:
                return JsonResponse({'error': 'Invalid action.'}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data.'}, status=400)
        except Exception as e:
            # Log the exception e for debugging
            return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Method not allowed.'}, status=405)