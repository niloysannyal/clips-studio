import type { RenderOpts } from './types'

export interface TemplatePreset {
  id: string
  name: string
  badge: string
  description: string
  format: 'shorts' | 'longform'
  renderOpts: RenderOpts
}

export const TEMPLATES: TemplatePreset[] = [
  {
    id: 'viral_split_70_30',
    name: 'Viral 70/30 Split',
    badge: '⚡ Recommended',
    description: 'Top 32% facecam, bottom 68% gameplay. Safe lower-third gold karaoke captions for maximum retention & views.',
    format: 'shorts',
    renderOpts: {
      gaming: {
        preset: 'split',
        divider: 0.32,
        order: 'cam_top',
        game_fit: 'fill',
        safe: 'shorts',
        cam: [0.0, 0.4315, 0.1979, 0.2148],
        game_box: [0.2674, 0.0, 0.4652, 1.0]
      },
      caption_style: {
        font: 'Impact',
        font_size: 84,
        color: '#FFFFFF',
        position: 'bottom',
        words_per_caption: 2,
        uppercase: true,
        highlight: true,
        highlight_color: '#FFE600'
      },
      watermark: {
        type: 'image',
        image_asset: '28b4dc654df23460.png',
        position: 'bottom_right',
        opacity: 0.85,
        scale: 0.18,
        padding: 0.04
      }
    }
  },
  {
    id: 'reaction_pip_circle',
    name: 'Reaction PiP (Circle)',
    badge: '🎯 Floating Cam',
    description: 'Full screen gameplay with floating circular reaction facecam and dynamic captions.',
    format: 'shorts',
    renderOpts: {
      gaming: {
        preset: 'circle_cam',
        game_fit: 'fill'
      },
      caption_style: {
        font: 'Impact',
        font_size: 84,
        color: '#FFFFFF',
        position: 'bottom',
        words_per_caption: 2,
        uppercase: true,
        highlight: true,
        highlight_color: '#FFE600'
      },
      watermark: {
        type: 'image',
        image_asset: '28b4dc654df23460.png',
        position: 'bottom_right',
        opacity: 0.85,
        scale: 0.18,
        padding: 0.04
      }
    }
  },
  {
    id: 'fullscreen_gameplay',
    name: 'Full Gameplay',
    badge: '📺 Action Focus',
    description: 'Full 9:16 vertical gameplay action without facecam.',
    format: 'shorts',
    renderOpts: {
      gaming: {
        preset: 'fullscreen',
        game_fit: 'fill'
      },
      caption_style: {
        font: 'Impact',
        font_size: 84,
        color: '#FFFFFF',
        position: 'bottom',
        words_per_caption: 2,
        uppercase: true,
        highlight: true,
        highlight_color: '#FFE600'
      },
      watermark: {
        type: 'image',
        image_asset: '28b4dc654df23460.png',
        position: 'bottom_right',
        opacity: 0.85,
        scale: 0.18,
        padding: 0.04
      }
    }
  },
  {
    id: 'cinematic_longform',
    name: 'Widescreen Longform',
    badge: '▭ 16:9 Landscape',
    description: 'Horizontal 1920x1080 full stream framing with clean bottom subtitles for YouTube longform monetization.',
    format: 'longform',
    renderOpts: {
      profile: 'landscape',
      caption_style: {
        font: 'Arial',
        font_size: 64,
        color: '#FFFFFF',
        position: 'bottom',
        words_per_caption: 4,
        uppercase: false,
        highlight: false
      },
      watermark: {
        type: 'image',
        image_asset: '28b4dc654df23460.png',
        position: 'top_right',
        opacity: 0.85,
        scale: 0.14,
        padding: 0.04
      }
    }
  }
]

export function getAllTemplates(): TemplatePreset[] {
  const custom: TemplatePreset[] = []
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem('custom-gaming-layouts') : null
    if (raw) {
      const list = JSON.parse(raw)
      for (const c of list) {
        if (!c || !c.name || !c.settings) continue
        custom.push({
          id: `custom_${c.id}`,
          name: c.name,
          badge: '⭐ Custom',
          description: `Custom layout preset "${c.name}"`,
          format: 'shorts',
          renderOpts: {
            gaming: c.settings,
            caption_style: {
              font: 'Impact',
              font_size: 84,
              color: '#FFFFFF',
              position: 'bottom',
              words_per_caption: 2,
              uppercase: true,
              highlight: true,
              highlight_color: '#FFE600',
              ...(c.settings?.caption_y !== undefined ? { caption_y: c.settings.caption_y } : {})
            },
            watermark: {
              type: 'image',
              image_asset: '28b4dc654df23460.png',
              position: 'bottom_right',
              opacity: 0.85,
              scale: 0.18,
              padding: 0.04
            }
          }
        })
      }
    }
  } catch {
    // ignore
  }
  return [...TEMPLATES, ...custom]
}

