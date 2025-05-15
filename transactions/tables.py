import django_tables2 as tables
from .models import Sale, Purchase


class SaleTable(tables.Table):
    items = tables.Column(accessor='get_items_display', verbose_name='Items')
    
    class Meta:
        model = Sale
        template_name = "django_tables2/semantic.html"
        fields = (
            'id',
            'date_added',
            'customer',
            'items',
            'sub_total',
            'grand_total',
            'tax_amount',
            'tax_percentage',
            'amount_paid',
            'amount_change'
        )
        order_by_field = 'sort'


class PurchaseTable(tables.Table):
    class Meta:
        model = Purchase
        template_name = "django_tables2/semantic.html"
        fields = (
            'item',
            'vendor',
            'order_date',
            'delivery_date',
            'quantity',
            'delivery_status',
            'price',
            'total_value'
        )
        order_by_field = 'sort'