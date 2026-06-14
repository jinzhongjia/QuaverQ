import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {LyricsDBusClient} from './dbusClient.js';
import {LyricOverlay} from './osdOverlay.js';
import {LyricPanelIndicator} from './panelIndicator.js';

export default class QuaverQLyricsExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._log = this.getLogger();

        this._osd = null;
        this._panel = null;

        this._client = new LyricsDBusClient({
            onLyricLoaded: (mid, lines, hasWordTiming, hasTranslation) => {
                this._log.debug(`lyric loaded: ${mid}, ${lines.length} lines`);
                this._osd?.setLyric(lines, hasWordTiming);
                this._panel?.setLyric(lines);
            },
            onActiveChanged: (line, word) => {
                this._osd?.setActive(line, word);
                this._panel?.setActive(line);
            },
            onDisconnected: () => {
                this._log.debug('QuaverQ disconnected');
                this._osd?.setLyric([], false);
                this._panel?.setLyric([]);
            },
        });

        this._settings.connectObject(
            'changed::display-mode', () => this._rebuildDisplays(),
            'changed::osd-font-size', () => this._osd?.updateStyle(),
            'changed::osd-bottom-margin', () => this._osd?.reposition(),
            'changed::osd-opacity', () => this._osd?.updateStyle(),
            'changed::show-translation', () => this._osd?.updateVisibility(),
            'changed::show-next-line', () => this._osd?.updateVisibility(),
            'changed::panel-max-width', () => this._panel?.updateStyle(),
            'changed::panel-position', () => this._rebuildPanel(),
            this,
        );

        this._buildDisplays();
        this._client.start();
    }

    disable() {
        this._client?.destroy();
        this._client = null;

        this._destroyOsd();
        this._destroyPanel();

        this._settings?.disconnectObject(this);
        this._settings = null;
        this._log = null;
    }

    _getMode() {
        return this._settings.get_string('display-mode');
    }

    _buildDisplays() {
        const mode = this._getMode();
        if (mode === 'osd' || mode === 'both')
            this._buildOsd();
        if (mode === 'panel' || mode === 'both')
            this._buildPanel();
    }

    _rebuildDisplays() {
        const mode = this._getMode();

        if (mode === 'osd' || mode === 'both') {
            if (!this._osd)
                this._buildOsd();
        } else {
            this._destroyOsd();
        }

        if (mode === 'panel' || mode === 'both') {
            if (!this._panel)
                this._buildPanel();
        } else {
            this._destroyPanel();
        }

        this._syncState();
    }

    _rebuildPanel() {
        const mode = this._getMode();
        if (mode === 'panel' || mode === 'both') {
            this._destroyPanel();
            this._buildPanel();
            this._syncState();
        }
    }

    _buildOsd() {
        if (this._osd)
            return;
        this._osd = new LyricOverlay(this._settings);
    }

    _buildPanel() {
        if (this._panel)
            return;
        const position = this._settings.get_string('panel-position');
        this._panel = new LyricPanelIndicator(this._settings, this._client);
        this._panel.addToPanel(position);
    }

    _destroyOsd() {
        if (!this._osd)
            return;
        this._osd.destroy();
        this._osd = null;
    }

    _destroyPanel() {
        if (!this._panel)
            return;
        this._panel.destroy();
        this._panel = null;
    }

    _syncState() {
        if (!this._client?.connected)
            return;

        const lines = this._client.lines;
        const hasWordTiming = this._client.hasWordTiming;

        this._osd?.setLyric(lines, hasWordTiming);
        this._panel?.setLyric(lines);
    }
}
