---
name: qq-music-design
description: Design guidelines for building music player / streaming UIs in the QQ Music PC style — layout (sidebar + main + playback bar), color tokens, typography, component specs (song lists, cards, lyric view, settings, popups), interaction patterns, and ready-to-use CSS variables. Use when designing, building, or auditing music-app screens, layouts, theming, or components.
---

# QQ Music Style Design Guide

This document provides comprehensive design guidelines for creating music software interfaces inspired by the QQ Music PC application. When building a music player or streaming application, follow these specifications for layout, color, typography, components, and interactions.

## Core Design Philosophy

The design language emphasizes clarity, content-first presentation, and intuitive navigation. Use a clean, bright aesthetic with strategic brand color accents to guide user attention. Balance complex functionality with a spacious, uncluttered appearance.

## Global Layout Structure

Use a classic three-zone layout:

| Zone | Position | Dimensions | Purpose |
|------|----------|-----------|---------|
| Left Sidebar | Fixed left | ~240px wide | Navigation, user profile, playlists |
| Main Content | Center fluid | Remaining width | Page content (home feed, playlists, search) |
| Playback Bar | Fixed bottom | ~80px tall, full width | Persistent playback controls |

The top title bar contains: user avatar + username + VIP badge (left), back/forward nav + search bar (center), and window controls (right).

## Color Palette

### Primary Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-brand-primary` | `#31C27C` | Active tabs, play button, selected checkboxes, highlighted text |
| `--color-brand-hover` | `#2CAF6F` | Hover state for brand-colored elements |
| `--color-brand-active` | `#28A065` | Pressed/active state |
| `--color-bg-main` | `#FFFFFF` | Main content background |
| `--color-bg-sidebar` | `#F5F5F7` | Sidebar and section backgrounds |
| `--color-bg-hover` | `rgba(0,0,0,0.04)` | Subtle hover for list items |
| `--color-text-primary` | `#333333` | Titles, song names |
| `--color-text-secondary` | `#999999` | Artist names, metadata, inactive text |
| `--color-border` | `#E0E0E0` | Standard borders and dividers |

### Lyric/Full-Screen Mode Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-lyric-bg-start` | `#FFF5E6` | Warm gradient start |
| `--color-lyric-bg-end` | `#FFE0B2` | Warm gradient end |
| `--color-lyric-highlight` | `#FF8C00` | Current lyric line |

### Badge/Tag Colors

- **VIP**: Green background with white text
- **Master Quality (臻品母带)**: Orange/gold background
- **Spatial Audio (全景声)**: Blue badge
- **Hi-Res**: Gold badge

## Typography

| Level | Size | Weight | Usage |
|-------|------|--------|-------|
| Page Title | 24–28px | Bold (600) | Section headings like "喜欢", "最近播放" |
| Section Header | 18–20px | Bold (600) | Sub-section titles |
| Primary Content | 14–16px | Regular/Medium (400–500) | Song titles |
| Secondary Content | 12–13px | Regular (400) | Artist names, album names, duration |
| Badges | 12px | Medium (500) | VIP, HQ, SQ tags |

Font stack: `-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif`

## Spacing and Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--spacing-xs` | 4px | Tight gaps (badge padding) |
| `--spacing-sm` | 8px | Small gaps |
| `--spacing-md` | 16px | Standard component padding |
| `--spacing-lg` | 24px | Page padding |
| `--spacing-xl` | 32px | Large section gaps |
| `--radius-sm` | 4px | Small thumbnails, badges |
| `--radius-md` | 8px | Standard cards |
| `--radius-lg` | 12px | Large cards, dialogs |
| `--radius-pill` | 20px | Pill buttons, search bar |
| `--radius-circle` | 50% | Avatars, play button |

## Component Specifications

### 1. Left Navigation Sidebar

Structure (top to bottom):
1. **User Profile**: Circular avatar + username + VIP badge
2. **Nav Icon Grid**: 2×2 grid of icon buttons (Home, Discover, Library, Charts)
3. **Function List**: Vertical items with icon + label + count (Liked·308, Recently Played·500, Local & Downloads, Queue)
4. **Playlist Section**: Header ("Created Playlists | Saved Playlists" + "+" button) followed by playlist items (32×32 thumbnail + name)

Active item: light gray background fill or brand green text/icon.

### 2. Playback Control Bar

Three-zone horizontal layout:

**Left Zone (~25% width):**
- Album art thumbnail: 50×50px, 4px radius
- Song title (bold) + artist name (gray) stacked vertically
- Action icons: Like (heart), Comment, Share, More (...)

**Center Zone (~50% width):**
- Control row: Loop mode → Previous → Play/Pause (large green circle, ~48px) → Next → Volume
- Progress row: Current time + seekable progress bar + total time

**Right Zone (~25% width):**
- Audio quality badge (HQ/SQ)
- Sound effects icon
- Lyrics toggle icon
- Playlist queue icon

### 3. Song List Table

| Column | Content | Width |
|--------|---------|-------|
| Song/Artist | 40×40 thumbnail + song title (bold) + badges + artist (gray below) | ~55% |
| Album | Album name text | ~30% |
| Duration | MM:SS format | ~15% |

Row height: ~64px. On hover, reveal action icons (Like, Download, Add to Playlist, More) replacing or overlaying the duration column.

### 4. Content Cards (Home/Discover)

**Playlist/Album Cards:**
- Square image with 8px radius
- Play count badge: bottom-right corner, semi-transparent dark background, white text
- Title below image (max 2 lines, ellipsis overflow)
- Grid layout: 4–5 columns with 16–20px gaps

**Banner/Featured Cards:**
- Larger rectangular card with 12px radius
- Text overlay on the image (title + subtitle)
- Green circular play button overlaid

On hover: show a centered play button overlay on the card image.

### 5. Playlist Detail Page

**Header:**
- Large cover art: ~160×160px, 8px radius
- Playlist title (page title size, bold)
- Creator info: avatar + name + tags
- Description text (gray, smaller)
- Action buttons row: Play (outlined), Download (outlined), Batch (outlined), Share (outlined) — all pill-shaped with icons

**Tabs:**
- Active tab: brand green text + green underline (2px)
- Inactive tab: gray text
- Examples: "Songs 24", "Recent Saves", "Comments"

### 6. Full-Screen Lyric View

**Layout:** Two-column split on a warm gradient background.

**Left column:**
- Vinyl record player animation (rotating disc with album art in center)
- Realistic turntable styling with arm

**Right column:**
- Center-aligned lyrics
- Current line: bold, larger font, orange/brand highlight color
- Upcoming lines: dark gray, normal weight
- Past lines: light gray, fading opacity

**Bottom:** Simplified control bar matching the gradient background, with essential controls only.

### 7. Settings Page

**Tab navigation:** Horizontal tabs at top (General, Downloads, Desktop Lyrics, Shortcuts, Audio Plugins, Network, Audio Devices). Active tab uses brand green text + underline.

**Content:** Grouped settings with section labels. Checkboxes use brand green fill when selected (circular checkboxes). Radio buttons for exclusive choices.

### 8. Audio Quality Popup

White card popup with 12px radius and subtle shadow. Two sections:
1. **Premium tier** (VIP exclusive): Master quality + Premium quality cards with icons
2. **Standard tier**: SQ Lossless, HQ High Quality, Standard — each with file size indicator and a green checkmark for the current selection.

### 9. Volume Control Popup

Vertical slider in a small white card popup. Green track with circular handle. Percentage display below the slider. Speaker icon at the bottom.

## Interaction Patterns

**Hover:** Reveal contextual actions on cards and list rows. Subtle background color change on sidebar items.

**Active/Selected:** Brand green for active tabs (text + underline), filled checkboxes, and selected sidebar items (background highlight).

**Empty States:** Centered illustration/icon + descriptive text + action button (e.g., "Add" or "Restore" on the Local Downloads page).

**Navigation:** Browser-style back/forward buttons. Sidebar for primary navigation. Tabs for content filtering within a page.

**Transitions:** Smooth fade for page transitions. Rotation animation for vinyl record. Scroll-based lyric highlighting.

## Z-Index Hierarchy

| Layer | Z-Index | Elements |
|-------|---------|----------|
| Base content | 1 | Main content area |
| Sidebar | 10 | Left navigation |
| Playback bar | 20 | Bottom control bar |
| Dropdowns | 30 | Volume popup, quality popup |
| Modals | 40 | Settings, dialogs |
| Tooltips | 50 | Hover tooltips |

## CSS Variables (Ready to Use)

```css
:root {
  /* Brand */
  --color-brand-primary: #31C27C;
  --color-brand-hover: #2CAF6F;
  --color-brand-active: #28A065;

  /* Backgrounds */
  --color-bg-main: #FFFFFF;
  --color-bg-sidebar: #F5F5F7;
  --color-bg-hover: rgba(0, 0, 0, 0.04);
  --color-bg-active: #EBEBEB;

  /* Text */
  --color-text-primary: #333333;
  --color-text-secondary: #999999;
  --color-text-inverse: #FFFFFF;

  /* Borders */
  --color-border: #E0E0E0;
  --color-divider-light: #F0F0F0;

  /* Lyric Mode */
  --color-lyric-bg-start: #FFF5E6;
  --color-lyric-bg-end: #FFE0B2;
  --color-lyric-highlight: #FF8C00;

  /* Typography */
  --font-family-base: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  --font-size-xs: 12px;
  --font-size-sm: 13px;
  --font-size-base: 14px;
  --font-size-lg: 16px;
  --font-size-xl: 18px;
  --font-size-xxl: 24px;
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-bold: 600;

  /* Layout */
  --sidebar-width: 240px;
  --playback-bar-height: 80px;

  /* Spacing */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;

  /* Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 20px;
  --radius-circle: 50%;

  /* Z-Index */
  --z-index-base: 1;
  --z-index-sidebar: 10;
  --z-index-playback-bar: 20;
  --z-index-dropdown: 30;
  --z-index-modal: 40;
  --z-index-tooltip: 50;
}
```


## Reference Screenshots

The `screenshots/` directory bundles 12 reference captures of the QQ Music PC app. Consult them when you need a concrete visual for a layout or component:

| File | Screen |
|------|--------|
| 01-home-idle.webp | Home feed (idle) |
| 02-home-playing.webp | Home feed (playing) |
| 03-daily-playlist.webp | Daily recommended playlist |
| 04-liked-songs.webp | Liked songs list |
| 05-recent-played.webp | Recently played |
| 06-local-downloads.webp | Local & downloads (empty/list) |
| 07-user-playlist.webp | User-created playlist detail |
| 08-lyric-view.webp | Full-screen lyric view |
| 09-lyric-volume.webp | Lyric view + volume popup |
| 10-lyric-quality.webp | Lyric view + audio quality popup |
| 11-public-playlist.webp | Public/shared playlist detail |
| 12-settings.webp | Settings page |
