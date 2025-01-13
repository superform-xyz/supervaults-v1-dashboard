window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        update_width: function() {
            return window.innerWidth;
        }
    }
});