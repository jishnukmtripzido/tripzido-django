# apps/core/pagination.py

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class CustomPagination(PageNumberPagination):
    page_size = 10  # default items per page
    page_size_query_param = "page_size"  # ?page_size=20
    max_page_size = 100  # max allowed

    def get_paginated_response(self, data):
        return Response(
            {
                "pagination": {
                    "total": self.page.paginator.count,
                    "page": self.page.number,
                    "page_size": self.get_page_size(self.request),
                    "total_pages": self.page.paginator.num_pages,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                },
                "results": data,
            }
        )
