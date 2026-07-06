/** Navegação padronizada dentro do iframe do portal operacional */
(function () {
    window.voltarPortal = function (url, titulo) {
        var destino = url || '/tela_boas_vindas';
        var rotulo = titulo || 'Início';
        if (window.parent && typeof window.parent.navegarPorUrl === 'function') {
            window.parent.navegarPorUrl(destino, rotulo);
            return false;
        }
        window.location.href = '/portal_operacional';
        return false;
    };

    window.irModulo = function (url, titulo) {
        if (window.parent && typeof window.parent.navegarPorUrl === 'function') {
            window.parent.navegarPorUrl(url, titulo);
            return false;
        }
        window.location.href = url;
        return false;
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-voltar-portal]').forEach(function (el) {
            el.addEventListener('click', function (e) {
                e.preventDefault();
                voltarPortal(el.dataset.voltarPortal || undefined, el.dataset.voltarTitulo || undefined);
            });
        });
    });
})();
