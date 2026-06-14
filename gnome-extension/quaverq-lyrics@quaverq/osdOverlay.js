import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export const LyricOverlay = GObject.registerClass(
class LyricOverlay extends St.BoxLayout {
    _init(settings) {
        super._init({
            style_class: 'quaverq-osd',
            orientation: Clutter.Orientation.VERTICAL,
            reactive: false,
            visible: false,
            x_align: Clutter.ActorAlign.CENTER,
        });

        this._settings = settings;
        this._lines = [];
        this._hasWordTiming = false;
        this._activeLine = -1;
        this._activeWord = -1;

        this._mainLine = new St.Label({
            style_class: 'quaverq-osd-main',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._mainLine.clutter_text.ellipsize = 0; // PANGO_ELLIPSIZE_NONE
        this._mainLine.clutter_text.line_wrap = false;
        this.add_child(this._mainLine);

        this._translationLine = new St.Label({
            style_class: 'quaverq-osd-translation',
            x_align: Clutter.ActorAlign.CENTER,
            visible: false,
        });
        this.add_child(this._translationLine);

        this._nextLine = new St.Label({
            style_class: 'quaverq-osd-next',
            x_align: Clutter.ActorAlign.CENTER,
            visible: false,
        });
        this.add_child(this._nextLine);

        Main.layoutManager.addTopChrome(this, {
            affectsInputRegion: false,
        });

        Main.layoutManager.connectObject(
            'monitors-changed', () => this._reposition(),
            this,
        );

        this._applyStyle();
    }

    setLyric(lines, hasWordTiming) {
        this._lines = lines;
        this._hasWordTiming = hasWordTiming;
        this._activeLine = -1;
        this._activeWord = -1;
        this._clearDisplay();
    }

    setActive(line, word) {
        const lineChanged = line !== this._activeLine;
        this._activeLine = line;
        this._activeWord = word;

        if (line < 0 || line >= this._lines.length) {
            this._hideSmooth();
            return;
        }

        if (lineChanged)
            this._renderLine();
        else if (this._hasWordTiming)
            this._renderWords();
    }

    updateStyle() {
        this._applyStyle();
    }

    updateVisibility() {
        const showTranslation = this._settings.get_boolean('show-translation');
        const showNext = this._settings.get_boolean('show-next-line');
        this._translationLine.visible = showTranslation && this._translationLine.text !== '';
        this._nextLine.visible = showNext && this._nextLine.text !== '';
    }

    reposition() {
        this._reposition();
    }

    _applyStyle() {
        const fontSize = this._settings.get_int('osd-font-size');
        const opacity = this._settings.get_double('osd-opacity');
        const bg = `background-color: rgba(0, 0, 0, ${opacity.toFixed(2)});`;
        this.set_style(bg);
        this._mainLine.set_style(`font-size: ${fontSize}px;`);
    }

    _reposition() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;

        const margin = this._settings.get_int('osd-bottom-margin');
        const y = monitor.y + monitor.height - this.height - margin;
        const x = monitor.x + Math.floor((monitor.width - this.width) / 2);
        this.set_position(x, y);
    }

    _renderLine() {
        const entry = this._lines[this._activeLine];
        if (!entry)
            return;

        const [_ts, text, translation, words] = entry;

        if (this._hasWordTiming && words && words.length > 0)
            this._renderWords();
        else
            this._mainLine.text = text;

        const showTranslation = this._settings.get_boolean('show-translation');
        if (showTranslation && translation) {
            this._translationLine.text = translation;
            this._translationLine.visible = true;
        } else {
            this._translationLine.text = '';
            this._translationLine.visible = false;
        }

        const showNext = this._settings.get_boolean('show-next-line');
        const nextIdx = this._activeLine + 1;
        if (showNext && nextIdx < this._lines.length) {
            const [, nextText] = this._lines[nextIdx];
            this._nextLine.text = nextText;
            this._nextLine.visible = true;
        } else {
            this._nextLine.text = '';
            this._nextLine.visible = false;
        }

        if (!this.visible) {
            this.opacity = 0;
            this.visible = true;
        }
        this.ease({
            opacity: 255,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => this._reposition(),
        });
        this._reposition();
    }

    _renderWords() {
        const entry = this._lines[this._activeLine];
        if (!entry)
            return;

        const [, , , words] = entry;
        if (!words || words.length === 0)
            return;

        const parts = words.map(([, , wText], i) => {
            const escaped = GLib.markup_escape_text(wText, -1);
            if (i < this._activeWord)
                return `<span color="#ffffff">${escaped}</span>`;
            if (i === this._activeWord)
                return `<span color="#31c27c">${escaped}</span>`;
            return `<span color="rgba(255,255,255,0.4)">${escaped}</span>`;
        });

        this._mainLine.clutter_text.set_markup(parts.join(''));
        this._reposition();
    }

    _clearDisplay() {
        this._mainLine.text = '';
        this._translationLine.text = '';
        this._translationLine.visible = false;
        this._nextLine.text = '';
        this._nextLine.visible = false;
        this._hideSmooth();
    }

    _hideSmooth() {
        if (!this.visible)
            return;
        this.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                this.visible = false;
            },
        });
    }

    destroy() {
        Main.layoutManager.disconnectObject(this);
        Main.layoutManager.removeChrome(this);
        super.destroy();
    }
});
