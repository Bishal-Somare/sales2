from django.contrib import admin
from django.urls import path, include

#custom
handler404 = 'accounts.views.custom_404_view'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
    path('staff/', include('accounts.urls')),
    path('transactions/', include('transactions.urls')),
    path('accounts/', include('accounts.urls')),
    path('invoice/', include('invoice.urls')),
    path('bills/', include('bills.urls'))
]
