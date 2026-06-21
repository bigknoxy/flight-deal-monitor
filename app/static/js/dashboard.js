// Dashboard JavaScript - HTMX init and Alpine.js components

document.addEventListener('DOMContentLoaded', function () {
    initSidebar();
    initAutoDismiss();
});

function initSidebar() {
    var toggle = document.getElementById('menu-toggle');
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');

    if (toggle && sidebar) {
        function openSidebar() {
            sidebar.classList.add('open');
            if (overlay) overlay.classList.add('open');
        }

        function closeSidebar() {
            sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('open');
        }

        toggle.addEventListener('click', function (e) {
            e.stopPropagation();
            if (sidebar.classList.contains('open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        if (overlay) {
            overlay.addEventListener('click', closeSidebar);
        }

        // Close on escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeSidebar();
        });
    }
}

function initAutoDismiss() {
    document.querySelectorAll('.toast').forEach(function (el) {
        setTimeout(function () {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.3s ease';
            setTimeout(function () { el.remove(); }, 300);
        }, 4000);
    });
}

// Handle HTMX after-swap events to reinitialize components
document.addEventListener('htmx:afterSwap', function () {
    initAutoDismiss();
    // Re-highlight active nav item based on current URL
    highlightActiveNav();
});

function highlightActiveNav() {
    var currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(function (el) {
        var href = el.getAttribute('href');
        if (href === currentPath) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });
}
