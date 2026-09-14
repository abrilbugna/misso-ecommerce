function toggleMenu() {
    const menu = document.getElementById('mobileMenu');
    menu.classList.toggle('active');
}
function toggleSearch() {
    const input = document.getElementById('search-input');
    input.classList.toggle('open');
    if (input.classList.contains('open')) input.focus();
}
function toggleSearchMobile() {
    const input = document.getElementById('search-input-mobile');
    const logo = document.getElementById('nav-logo');
    input.classList.toggle('open');
    if (input.classList.contains('open')) {
        logo.classList.add('hidden');
        input.focus();
    } else {
        logo.classList.remove('hidden');
    }
}
