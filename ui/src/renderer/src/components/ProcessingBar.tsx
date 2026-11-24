import { useEffect, useRef, useState } from 'react'
import {
  applyEvent,
  currentFraction,
  emptyProgress,
  etaSeconds,
  formatEta,
  progressStore
} from '../lib/jobProgress'
import { api } from '../lib/api'
import { useEvents } from '../lib/useEvents'
import { useJobWatch } from '../lib/useJobWatch'
import { t } from '../lib/i18n'

/** Live progress for the running job: stage label, percent bar, an estimated
 *  time remaining that ticks down, and a Cancel button. Hidden when idle. */
export default function ProcessingBar(): JSX.Element | null {
  const [progress, setProgress] = useState(progressStore.current)
  const [now, setNow] = useState(Date.now())
  const [cancelling, setCancelling] = useState(false)
  const lastEventAt = useRef(Date.now())

  useEvents((e) => {
    lastEventAt.current = Date.now()
    progressStore.current = applyEvent(progressStore.current, e)
    setProgress(progressStore.current)
    if (e.type === 'job' && ['done', 'failed', 'cancelled'].includes(e.status ?? ''))
      setCancelling(false)
  })

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  // If a render job is running, fetch clip title to display exact clip info
  useEffect(() => {
    if (!progress.active || progress.title) return
    let active = true
    const checkRunning = async (): Promise<void> => {
      try {
        const q = await api.queue()
        const running = q.processing[0]
        if (!running || !active) return
        if (running.type === 'render') {
          const clipId = running.settings?.clip_id
          if (clipId) {
            const videos = await api.videos()
            for (const v of videos) {
              const clips = await api.clips(v.video_id)
              const match = clips.find((c) => c.id === clipId)
              if (match && active) {
                const dur = Math.round(match.end_s - match.start_s)
                const title = `Clip #${clipId}: "${match.title || match.hook || 'Clip'}" (${dur}s)`
                progressStore.current = {
                  ...progressStore.current,
                  title,
                  label: 'Re-rendering 9:16 layout & framing (FFmpeg)',
                  jobType: 'render',
                  clipId,
                  clipDuration: dur
                }
                setProgress(progressStore.current)
                break
              }
            }
          }
        }
      } catch {
        // ignore
      }
    }
    void checkRunning()
    return () => {
      active = false
    }
  }, [progress.active, progress.title])

  // The bar used to be cleared ONLY by a terminal event, and would claim to be
  // processing forever if that event went missing. useJobWatch is where that
  // lesson now lives, so the Dashboard and the clip list get it too.
  useJobWatch({
    active: progress.active,
    lastEventAt,
    onSettled: () => {
      progressStore.current = { ...emptyProgress }
      setProgress(progressStore.current)
      setCancelling(false)
    }
  })

  if (!progress.active) return null
  const isRender = progress.jobType === 'render' || progress.label.toLowerCase().includes('re-render')
  const eta = etaSeconds(progress, now)
  const pct = Math.round(currentFraction(progress, now) * 100)
  const elapsed = Math.max(0, Math.round((now - progress.startedAt) / 1000))

  // Remote rendering set to one worker that isn't there: the clips wait for
  // it, and this brings them back to this PC instead.
  const waiting = Boolean(progress.remote?.startsWith('waiting for'))
  const renderHere = async (): Promise<void> => {
    if (!progress.videoId) return
    try {
      await api.renderLocally(progress.videoId)
    } catch {
      // the next progress event says where the clips are
    }
  }

  const cancel = async (): Promise<void> => {
    if (!progress.videoId) return
    setCancelling(true)
    try {
      await api.cancelProcessing(progress.videoId)
    } catch {
      setCancelling(false)
    }
  }

  return (
    <div className="card space-y-2" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium truncate">
          {progress.title ? `${progress.title} — ` : ''}
          {progress.label || (isRender ? 'Re-rendering 9:16 layout & framing (FFmpeg)' : 'Working…')}
        </p>
        <div className="flex items-center gap-3 shrink-0">
          <p className="text-xs text-muted tabular-nums">
            <span className="font-semibold text-accent">{pct}%</span>
            <span> · {elapsed}s elapsed</span>
            <span>
              {' '}·{' '}
              {eta !== null
                ? `~${formatEta(eta)} left`
                : 'calculating…'}
            </span>
          </p>
          {/* Reachable from wherever the bar is shown: while a long batch
              runs, the queue is the screen that answers "what's left?" */}
          <button
            className="btn-ghost !px-2.5 !py-1 text-xs"
            onClick={() => window.dispatchEvent(new CustomEvent('open-queue'))}
          >
            Queue
          </button>
          {waiting && (
            <button className="btn-ghost !px-2.5 !py-1 text-xs" onClick={renderHere}>
              Render here instead
            </button>
          )}
          <button
            className="btn-ghost !px-2.5 !py-1 text-xs"
            onClick={cancel}
            disabled={cancelling || !progress.videoId}
          >
            {cancelling ? t('Cancelling…') : t('Cancel')}
          </button>
        </div>
      </div>
      <div
        className="h-2 rounded-full bg-raised overflow-hidden"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t('Video processing progress')}
      >
        <div
          className="h-full bg-accent rounded-full transition-[width] duration-700"
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
    </div>
  )
}
