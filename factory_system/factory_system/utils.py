def is_mobile_device(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    mobile_keywords = [
        'mobile', 'android', 'iphone', 'ipad', 'ipod', 
        'blackberry', 'windows phone', 'webos'
    ]
    return any(keyword in user_agent for keyword in mobile_keywords)


def get_paginate_by(request, desktop_count=20, mobile_count=10):
    if is_mobile_device(request):
        return mobile_count
    return desktop_count
