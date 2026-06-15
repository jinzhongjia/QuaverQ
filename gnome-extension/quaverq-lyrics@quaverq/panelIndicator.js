import GObject from 'gi://GObject';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

export const LyricPanelIndicator = GObject.registerClass(
class LyricPanelIndicator extends PanelMenu.Button {
    _init(settings, dbusClient) {
        super._init(0.5, 'QuaverQ Lyrics', false);

        this._settings = settings;
        this._dbusClient = dbusClient;
        this._activeLine = -1;
        this._lines = [];

        const box = new St.BoxLayout({
            style_class: 'panel-status-indicators-box',
        });

        this._icon = new St.Label({
            style_class: 'quaverq-panel-icon',
            text: '♪',
            y_align: Clutter.ActorAlign.CENTER,
        });
        box.add_child(this._icon);

        this._label = new St.Label({
            style_class: 'quaverq-panel-label',
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
        });
        this._label.clutter_text.ellipsize = 3;
        box.add_child(this._label);

        this.add_child(box);

        this.menu.connectObject(
            'open-state-changed', (_menu, open) => {
                if (open)
                    this._populateMenu();
            },
            this,
        );

        this._applyStyle();
        this.visible = false;
    }

    setLyric(lines, _hasWordTiming) {
        this._lines = lines;
        this._activeLine = -1;
        this._label.text = '';
        this.visible = false;
    }

    setActive(line, _word) {
        if (line === this._activeLine)
            return;
        this._activeLine = line;

        if (line < 0 || line >= this._lines.length) {
            this._label.text = '';
            this.visible = false;
            return;
        }

        const [, text] = this._lines[line];
        this._label.text = text;
        this.visible = true;
    }

    updateStyle() {
        this._applyStyle();
    }

    _applyStyle() {
        const maxWidth = this._settings.get_int('panel-max-width');
        this._label.set_style(`max-width: ${maxWidth}px;`);
    }

    _populateMenu() {
        this.menu.removeAll();

        if (!this._dbusClient.connected) {
            this.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                'QuaverQ is not running', {reactive: false}
            ));
            return;
        }

        this._dbusClient.getWindowAsync(3, 3).then(result => {
            this.menu.removeAll();

            if (!result || !result.window || result.window.length === 0) {
                this.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                    'No lyrics', {reactive: false}
                ));
                return;
            }

            const {window: lines, activeInWindow} = result;
            lines.forEach(([, text, translation], i) => {
                let label = text;
                if (translation)
                    label += `  ${translation}`;

                const item = new PopupMenu.PopupMenuItem(label, {reactive: false});
                if (i === activeInWindow)
                    item.add_style_class_name('quaverq-menu-active');
                this.menu.addMenuItem(item);
            });
        });
    }

    addToPanel(position) {
        if (position === 'right') {
            Main.panel.addToStatusArea('quaverq-lyrics', this, -1, 'center');
        } else {
            Main.panel.addToStatusArea('quaverq-lyrics', this, 0, 'center');
        }
    }

    destroy() {
        this.menu.disconnectObject(this);
        super.destroy();
    }
});
