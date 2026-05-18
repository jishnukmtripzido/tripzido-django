from rest_framework.response import Response

def success_response(data=None, message="Success", status=200):
    return Response({
        "success": True,
        "message": message,
        "data": data or {}
    }, status=status)

def error_response(message="Error", errors=None, status=400):
    return Response({
        "success": False,
        "message": message,
        "errors": errors or {}
    }, status=status)




#  return error_response(
#             message="Validation failed",
#             errors=serializer.errors,
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#   return success_response(
#             data=serializer.data,
#             message="Account group retrieved successfully",
#             status=status.HTTP_200_OK,
#         )
