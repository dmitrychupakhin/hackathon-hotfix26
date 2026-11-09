"""Provider metadata constrains the configured cap; unavailable metadata stays conservative."""

MIN_CONTEXT_WINDOW = 4096


def context_budget(settings, model, reported_windows):
    reported = reported_windows.get(model)
    return {
        "context_window_tokens": min(settings.context_window, reported or 160000),
        "reported_context_window_tokens": reported,
        "configured_cap_tokens": settings.context_window,
        "source": "provider" if reported else "fallback",
        "max_context_reductions": settings.max_context_reductions,
        "min_context_window_tokens": MIN_CONTEXT_WINDOW,
    }
