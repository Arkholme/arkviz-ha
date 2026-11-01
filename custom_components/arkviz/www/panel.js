// The element Home Assistant puts in its sidebar for ArkViz. It holds ArkViz in a frame of its own, so ArkViz keeps
// its own page, styles and history, and hands the frame each new `hass` it's given. src/ha/panel.ts reads it there.

// The app's page sits beside this file, fetched afresh for each version as this file is
const page = new URL('app/index.html', import.meta.url)
page.searchParams.set('v', new URL(import.meta.url).searchParams.get('v') ?? '')

class ArkVizPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass
    if (!this._frame) return
    this._frame.hass = hass
    this._frame.dispatchEvent(new Event('hass'))
  }

  get hass() {
    return this._hass
  }

  connectedCallback() {
    // Home Assistant moves panels between pages, which connects them again
    if (this.shadowRoot) return
    const root = this.attachShadow({ mode: 'open' })
    const style = document.createElement('style')
    // Home Assistant doesn't size its panels, so this one fills the window's height itself
    style.textContent = ':host { display: block; height: 100vh; height: 100dvh; } iframe { display: block; width: 100%; height: 100%; border: 0; }'
    const frame = document.createElement('iframe')
    frame.title = 'ArkViz'
    frame.hass = this._hass
    frame.src = page.href
    root.append(style, frame)
    this._frame = frame
  }
}

if (!customElements.get('arkviz-panel')) customElements.define('arkviz-panel', ArkVizPanel)
