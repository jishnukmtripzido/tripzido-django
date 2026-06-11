from django.shortcuts import render

# Create your views here.
from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.administrations.services import CancellationPolicyService
from apps.administrations.serializers import CancellationPolicySerializer
from apps.core.responses import success_response, error_response


class CancellationPolicyView(GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, **kwargs):
        # kwargs absorbs any path params (e.g. vehicleId) — policy is platform-wide
        data = CancellationPolicyService.get_current_policy()

        if data is None:
            return error_response(
                message="No cancellation policy found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CancellationPolicySerializer(data)
        return success_response(
            data=serializer.data,
            message="Cancellation policy retrieved successfully",
            status=status.HTTP_200_OK,
        )
