import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {LyricsDBusClient} from './dbusClient.js';
import {LyricPanelIndicator} from './panelIndicator.js';

export default class QuaverQLyricsExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._log = this.getLogger();

        this._panel = null;

        this._client = new LyricsDBusClient({
            onLyricLoaded: (mid, lines, hasWordTiming, hasTranslation) => {
                this._log.debug(`lyric loaded: ${mid}, ${lines.length} lines`);
                this._panel?.setLyric(lines, hasWordTiming);
            },
            onActiveChanged: (line, word) => {
                this._panel?.setActive(line, word);
            },
            onDisconnected: () => {
                this._log.debug('QuaverQ disconnected');
                this._panel?.setLyric([], false);
            },
        });

        this._settings.connectObject(
            'changed::panel-max-width', () => this._panel?.updateStyle(),
            'changed::panel-position', () => this._rebuildPanel(),
            this,
        );

        this._buildPanel();
        this._client.start();
    }

    disable() {
        this._client?.destroy();
        this._client = null;

        this._destroyPanel();

        this._settings?.disconnectObject(this);
        this._settings = null;
        this._log = null;
    }

    _buildPanel() {
        if (this._panel)
            return;
        const position = this._settings.get_string('panel-position');
        this._panel = new LyricPanelIndicator(this._settings, this._client);
        this._panel.addToPanel(position);
    }

    _destroyPanel() {
        if (!this._panel)
            return;
        this._panel.destroy();
        this._panel = null;
    }

    _rebuildPanel() {
        this._destroyPanel();
        this._buildPanel();
        this._syncState();
    }

    _syncState() {
        if (!this._client?.connected)
            return;
        const lines = this._client.lines;
        const hasWordTiming = this._client.hasWordTiming;
        this._panel?.setLyric(lines, hasWordTiming);
    }
}
