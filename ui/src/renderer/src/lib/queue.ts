import type { Clip, JobOptions, QueueJob, QueueSnapshot } from './types'
import type { JobProgress } from './jobProgress'
import { etaSeconds } from './jobProgress'
import { describeSport } from './sports'

/** Pure queue helpers — no React, no fetch.
 *
 *  Everything here is a function of the snapshot the server sent, so the
 *  queue's rules can be reasoned about (and changed) without touching a
 *  component, and no component grows its own private copy of them. */

/** What to call a queue row.
 *
 *  `display_title` comes from the videos table and is empty until the
 *  download names the video — and for jobs queued before this feature
 *  existed. The URL is the honest fallback; inventing a name would be worse
 *  than showing the thing the user actually pasted. */
export function jobLabel(job: QueueJob, clipMap?: Map<number, Clip>): string {
  if (job.type === 'render') {
    const clipId = job.settings?.clip_id
    if (clipId) {
      const clip = clipMap?.get(clipId)
      if (clip) {
        const dur = Math.round(clip.end_s - clip.start_s)
        const title = clip.title || clip.hook || `Clip #${clipId}`
        return `Clip #${clipId}: "${title}" (${dur}s)`
      }
      return `Clip #${clipId} (Re-rendering 9:16)`
    }
    return 'Re-rendering a clip'
  }
  if (job.display_title) return job.display_title
  if (job.type === 'translate') return 'Subtitles & dubbing'
  if (!job.url) return `Job ${job.id}`
  if (job.url.startsWith('local:')) return 'Local video file'
  try {
    const u = new URL(job.url)
    return `${u.hostname.replace(/^www\./, '')}${u.pathname}`
  } catch {
    return job.url
  }
}

/** Which site a job's video came from, for a small chip on the row.
 *
 *  Matched against the parsed hostname rather than the whole URL. Testing
 *  /twitch\.tv/ against the raw string also matches
 *  `example.com/watch?ref=twitch.tv` and `twitch.tv.phishing.example`, which
 *  puts a Twitch chip on a row that has nothing to do with Twitch. */
export function sourceOf(url: string): string {
  if (!url) return ''
  if (url.startsWith('local:')) return 'Local file'

  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '').toLowerCase()
  } catch {
    return 'Link'
  }

  // Exact host, or a subdomain of it — never a substring.
  const from = (domain: string): boolean => host === domain || host.endsWith(`.${domain}`)
  if (from('youtube.com') || from('youtu.be')) return 'YouTube'
  if (from('twitch.tv')) return 'Twitch'
  if (from('kick.com')) return 'Kick'
  return 'Link'
}

/** The settings that actually differ from the defaults, as short chips.
 *  Only what was chosen is listed — a row of "off" badges is noise. */
export function describeOptions(o: JobOptions | undefined): string[] {
  if (!o) return []
  const chips: string[] = []
  if (o.captions === false) chips.push('No captions')
  if (o.long_clips) chips.push('60s+')
  if (o.podcast) chips.push('Podcast')
  if (o.vertical_live) chips.push('Vertical Live')
  if (o.gaming) chips.push('Gaming / Reaction')
  if (o.sport) chips.push(describeSport(o.sport))
  if (o.longform)
    chips.push(
      `Longform · ${String(o.longform.mode ?? '').replace(/_/g, ' ')}${o.longform.shorts ? ' + 9:16 Shorts' : ''}`
    )
  if (o.watermark_profile_id) chips.push('Watermark')
  if (o.filter && o.filter !== 'none') chips.push(`Filter · ${o.filter}`)
  if (typeof o.max_clips === 'number') chips.push(`Max ${o.max_clips} clips`)
  if (typeof o.min_score === 'number') chips.push(`Score ≥ ${o.min_score}`)
  if (o.focus) chips.push(`Direction · ${o.focus.length > 40 ? `${o.focus.slice(0, 40)}…` : o.focus}`)
  if (o.force) chips.push('Reprocess')
  if (o.clip_id) {
    chips.push('9:16 Re-render')
    const gaming = (o as any).render_opts?.gaming
    if (gaming?.preset) {
      chips.push(`Layout · ${gaming.preset}`)
    }
  }
  return chips
}

export interface QueueCounts {
  total: number
  renders: number
  processes: number
  translates: number
  summary: string
}

export function queueCounts(snapshot: QueueSnapshot | null): QueueCounts {
  if (!snapshot) return { total: 0, renders: 0, processes: 0, translates: 0, summary: '0 videos remaining' }
  const allActive = [...snapshot.processing, ...snapshot.queued]
  let renders = 0
  let processes = 0
  let translates = 0
  for (const j of allActive) {
    if (j.type === 'render') renders++
    else if (j.type === 'translate') translates++
    else processes++
  }
  const total = allActive.length
  let summary = ''
  if (processes === 0 && renders > 0) {
    summary = `${renders} ${renders === 1 ? 'clip remaining' : 'clips remaining'}`
  } else if (processes > 0 && renders > 0) {
    summary = `${processes} ${processes === 1 ? 'video' : 'videos'}, ${renders} ${renders === 1 ? 'clip' : 'clips'} remaining`
  } else {
    summary = `${total} ${total === 1 ? 'video remaining' : 'videos remaining'}`
  }
  return { total, renders, processes, translates, summary }
}

/** Seconds until the whole queue is done.
 *
 *  Two halves from two sources, deliberately. The waiting videos are the
 *  server's call — it has the processing history. The running video is the
 *  UI's, because the live progress fraction is already here and extrapolating
 *  from it beats any historical average once a video is underway. Falls back
 *  to the server's per-video figure while progress is too young to trust. */
export function queueEta(
  snapshot: QueueSnapshot | null,
  live: JobProgress,
  now: number
): number | null {
  if (!snapshot) return null
  const running = snapshot.processing
  const queued = snapshot.queued
  if (running.length === 0 && queued.length === 0) return null

  let totalSeconds = 0
  // Queued jobs
  for (const job of queued) {
    if (job.type === 'render') {
      totalSeconds += 83
    } else if (job.type === 'translate') {
      totalSeconds += 60
    } else {
      totalSeconds += snapshot.estimate.per_video_seconds || 3600
    }
  }

  // Running jobs
  for (const job of running) {
    if (job.type === 'render') {
      const fromProgress = etaSeconds(live, now)
      totalSeconds += fromProgress !== null ? fromProgress : 83
    } else {
      const fromProgress = etaSeconds(live, now)
      totalSeconds += fromProgress ?? (snapshot.estimate.per_video_seconds || 3600)
    }
  }

  return Math.round(totalSeconds)
}

/** "2h 47m" / "18m" / "45s". Coarser than the per-clip timer on purpose:
 *  to the second is false precision on an hour-long estimate. */
export function formatQueueEta(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

/** How long a finished job took, from its own timestamps. */
export function ranFor(job: QueueJob): string | null {
  if (!job.started_at || !job.finished_at) return null
  const ms = new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()
  if (!Number.isFinite(ms) || ms <= 0) return null
  return formatQueueEta(ms / 1000)
}

/** Total videos still to process, including the one running. */
export function remainingCount(snapshot: QueueSnapshot | null): number {
  if (!snapshot) return 0
  return snapshot.processing.length + snapshot.queued.length
}
