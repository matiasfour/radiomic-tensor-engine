"""
URL configuration for dki_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve

import os
from pathlib import Path as _Path

# Resolve the .. so Django static_serve can find the files
FRONTEND_DIST = str((_Path(settings.BASE_DIR) / '..' / 'frontend' / 'dist').resolve())

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('dki_core.urls')),

    # Serve media files (generated NIfTI, PDFs, DICOM archives) in all modes.
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),

    # Serve frontend assets explicitly (JS, CSS, fonts) so the catch-all
    # below never returns index.html for them (MIME-type fix).
    re_path(r'^assets/(?P<path>.*)$', static_serve, {'document_root': os.path.join(FRONTEND_DIST, 'assets')}),

    # Catch-all → React SPA (must remain last)
    re_path(r'^.*$', TemplateView.as_view(template_name='index.html')),
]
