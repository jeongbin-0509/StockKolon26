(() => {
    const button = document.querySelector('.scroll-to-top');
    const topLink = document.querySelector('header .logo-link');

    function updateVisibility() {
        button.hidden = window.scrollY < window.innerHeight;
    }

    button.addEventListener('click', () => {
        topLink.focus({ preventScroll: true });
        window.scrollTo({ top: 0 });
    });

    window.addEventListener('scroll', updateVisibility, { passive: true });
    window.addEventListener('resize', updateVisibility);
    window.addEventListener('pageshow', updateVisibility);
    updateVisibility();
})();
