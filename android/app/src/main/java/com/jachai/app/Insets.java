package com.jachai.app;

import android.view.View;

import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

/** Edge-to-edge helper: the verdict colour fills behind the status bar, the content stays clear of it. */
final class Insets {
    private Insets() {}

    static void padForSystemBars(View view) {
        final int left = view.getPaddingLeft(), top = view.getPaddingTop();
        final int right = view.getPaddingRight(), bottom = view.getPaddingBottom();
        ViewCompat.setOnApplyWindowInsetsListener(view, (v, windowInsets) -> {
            androidx.core.graphics.Insets bars = windowInsets.getInsets(
                    WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.ime());
            v.setPadding(left + bars.left, top + bars.top, right + bars.right, bottom + bars.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
    }
}
