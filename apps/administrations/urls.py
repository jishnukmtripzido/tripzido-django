from django.urls import path
from apps.administrations.views import CancellationPolicyView

urlpatterns = [
    path(
        "cancellation-policy/",
        CancellationPolicyView.as_view(),
        name="cancellation-policy",
    ),
]
