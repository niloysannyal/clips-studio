import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { getExportFolder, pickExportFolder, setExportFolder } from '../lib/exportFolder'
import { Folder, Scissors } from './icons'
import type { Clip, PluginNote, RenderOpts } from '../lib/types'
import { t } from '../lib/i18n'
import { sportMoment } from '../lib/sports'
import { suggestionLine } from '../lib/editSuggestions'
import { TEMPLATES, type TemplatePreset } from '../lib/templates'

const CHANNELS = ['text', 'audio', 'visual', 'reaction', 'engagement'] as const

function formatTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  }
  return `${m}:${sec.toString().padStart(2, '0')}`
}

/** A clip's plugin notes, one line per plugin (and version), in the order they came. */
function pluginNotes(notes: PluginNote[] | undefined): { key: string; who: string; texts: string[] }[] {
  const out: { key: string; who: string; texts: string[] }[] = []
  for (const n of notes ?? []) {
    if (!n?.text) continue
    const key = `${n.plugin}@${n.version ?? ''}`
    const line = out.find((l) => l.key === key)
    if (line) line.texts.push(n.text)
    else out.push({ key, who: `${n.name || n.plugin}${n.version ? ` ${n.version}` : ''}`, texts: [n.text] })
  }
  return out
}

export default function ClipEditor({
  clip,
  onChanged,
  onOpenEditor,
  onPublish
}: {
  clip: Clip
  onChanged: () => void
  onOpenEditor: () => void
  /** Publish this one clip. Absent when no provider is set up, which hides
   *  the button rather than showing one that can only apologise. */
  onPublish?: () => void
}): JSX.Element {
  const [title, setTitle] = useState(clip.title)
  const [description, setDescription] = useState(clip.description)
  const [hashtags, setHashtags] = useState(clip.hashtags.join(' '))
  const [start, setStart] = useState(clip.start_s)
  const [end, setEnd] = useState(clip.end_s)
  const [folder, setFolder] = useState('')
  const [activeRenderOpts, setActiveRenderOpts] = useState<RenderOpts>(clip.render_opts ?? {})
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('viral_split_70_30')
  const [showExactNumbers, setShowExactNumbers] = useState(false)

  // Default the export destination to the remembered folder / OS Downloads.
  useEffect(() => {
    getExportFolder().then(setFolder)
  }, [])
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    setTitle(clip.title)
    setDescription(clip.description)
    setHashtags(clip.hashtags.join(' '))
    setStart(clip.start_s)
    setEnd(clip.end_s)
    setActiveRenderOpts(clip.render_opts ?? {})
    setNotice(null)
  }, [clip.id])

  const flash = (msg: string): void => {
    setNotice(msg)
    setTimeout(() => setNotice(null), 4000)
  }

  const run = async (label: string, fn: () => Promise<void>): Promise<void> => {
    setBusy(label)
    try {
      await fn()
    } catch (e) {
      flash(`Error: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(null)
    }
  }

  const saveMetadata = (): Promise<void> =>
    run('save', async () => {
      await api.patchClip(clip.id, {
        title,
        description,
        hashtags: hashtags.split(/\s+/).filter(Boolean)
      })
      flash('Saved')
      onChanged()
    })

  const rerender = (): Promise<void> =>
    run('render', async () => {
      const range = start !== clip.start_s || end !== clip.end_s ? { start, end } : undefined
      await api.rerenderClip(clip.id, range, activeRenderOpts)
      flash('Re-render queued with template — watch the Dashboard / Queue')
    })

  const exportOne = (): Promise<void> =>
    run('export', async () => {
      const res = await api.exportClip(clip.id, folder)
      flash(res.exported.length ? `Exported: ${res.exported[0]}` : 'Nothing exported')
      onChanged() // exporting stars the clip; show it on its card
    })

  return (
    <div className="card space-y-4">
      <video
        key={clip.id}
        src={api.mediaUrl(clip.id)}
        controls
        aria-label={`Preview of clip: ${clip.title || clip.hook || 'untitled'}. Captions are burned into the video.`}
        className="w-full rounded-lg bg-base max-h-96"
      />

      <button
        onClick={onOpenEditor}
        className="btn-accent w-full !py-3 text-base font-semibold"
        title={t("Open the editor: trim, cut, mute words, censor, color, captions, AI edit")}
      >
        <span className="inline-flex items-center gap-2 justify-center">
          <Scissors size={16} /> Edit this clip
        </span>
      </button>

      <div className="flex gap-2 flex-wrap text-xs items-center">
        {CHANNELS.map((ch) => (
          <span key={ch} className="bg-raised px-2 py-1 rounded-md text-muted">
            {ch} <span className="text-ink font-semibold">{clip.scores[ch] ?? '–'}</span>
          </span>
        ))}
        {clip.scores.game != null && (
          // A match is scored with the same evidence a gaming stream gets.
          <span
            className="bg-raised px-2 py-1 rounded-md text-muted"
            title={clip.render_opts?.sport ? 'What the crowd and the whistle marked' : 'Scored as a gaming stream'}
          >
            {clip.render_opts?.sport ? 'match' : 'game'}{' '}
            <span className="text-ink font-semibold">{clip.scores.game}</span>
            {clip.scores.game_bonus ? <span className="text-accent"> +{clip.scores.game_bonus}</span> : null}
          </span>
        )}
        {clip.scores.sport_label && (
          <span className="bg-raised px-2 py-1 rounded-md text-ink" title={t("The match moment this clip is")}>
            {sportMoment(clip.scores)}
            {clip.scores.sport_bonus ? <span className="text-accent"> +{clip.scores.sport_bonus}</span> : null}
          </span>
        )}
      </div>
      {clip.scores.game_why && <p className="text-xs text-muted -mt-2">{clip.scores.game_why}</p>}
      {clip.scores.sport_why && (
        <p className="text-xs text-muted -mt-2" title={t("What marked this moment")}>
          {clip.scores.sport_why}
        </p>
      )}
      {clip.scores.plugin && (
        <p className="text-xs text-muted -mt-2" title={t("The Marketplace pipeline that found this moment, in its own words")}>
          Found by {clip.scores.plugin} {clip.scores.plugin_version}
          {clip.scores.plugin_label ? `: ${clip.scores.plugin_label}` : ''}
          {clip.scores.plugin_why ? ` · ${clip.scores.plugin_why}` : ''}
        </p>
      )}
      {/* Rate & understand (plugins/steps.py): each rating in the order it was
          applied (the last one counts), the score before any, and the notes. */}
      {(clip.scores.plugin_ratings ?? []).map((r, i) => (
        <p
          key={`rating-${i}`}
          className="text-xs text-muted -mt-2"
          title={t("A Marketplace plugin’s score for this moment, in its own words")}
        >
          Rated {r.score} by {r.name || r.plugin}
          {r.version ? ` ${r.version}` : ''}
          {r.reason ? ` · ${r.reason}` : ''}
        </p>
      ))}
      {clip.scores.found_score != null && (
        <p className="text-xs text-muted -mt-2" title={t("The score this moment had before any plugin rated it")}>
          Score when found: {clip.scores.found_score}
        </p>
      )}
      {pluginNotes(clip.scores.plugin_notes).map((n) => (
        <p
          key={n.key}
          className="text-xs text-muted -mt-2"
          title={t("What a Marketplace plugin said happens in this moment. Clips Kitty gives notes like this to the AI when it writes a new clip’s title, description and hashtags.")}
        >
          Notes from {n.who}: {n.texts.join(' · ')}
        </p>
      ))}
      {/* Suggest edits (plugins/steps.py suggest_edits): what each plugin
          suggested, and what came of it. They are used in the editor. */}
      {(clip.scores.plugin_edits ?? [])
        .filter((e) => e && typeof e.id === 'string' && e.edit)
        .map((e) => (
          <p
            key={`edit-${e.id}`}
            className="text-xs text-muted -mt-2"
            title={t("An edit a Marketplace plugin suggested for this clip. Open the editor to use it or hide it.")}
          >
            {suggestionLine(e, { start: clip.start_s, end: clip.end_s })}
          </p>
        ))}
      {clip.scores.intent_why && (
        <p className="text-xs text-muted -mt-2" title={t("Points from the clip direction given with this video")}>
          Direction +{clip.scores.intent}: {clip.scores.intent_why}
          {clip.scores.required ? ` · kept as asked (${clip.scores.required})` : ''}
        </p>
      )}

      <div className="space-y-3">
        <div>
          <label className="label">Title</label>
          <input className="input mt-1" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="label">Description</label>
          <textarea
            className="input mt-1 h-20 resize-none"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Hashtags (space-separated)</label>
          <input className="input mt-1" value={hashtags} onChange={(e) => setHashtags(e.target.value)} />
        </div>

        {/* --- Master Viral Templates --- */}
        <div className="rounded-lg border border-accent/30 bg-accent/5 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-accent">Viral Format Templates</span>
            <span className="text-[11px] text-muted">1-Click Layout & Captions</span>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {TEMPLATES.map((tmpl) => {
              const active = selectedTemplateId === tmpl.id
              return (
                <button
                  key={tmpl.id}
                  type="button"
                  onClick={() => {
                    setSelectedTemplateId(tmpl.id)
                    setActiveRenderOpts(tmpl.renderOpts)
                    flash(`Applied ${tmpl.name}! Click 'Re-render' to render video.`)
                  }}
                  className={`text-left p-2 rounded-md border text-xs transition-all ${
                    active
                      ? 'border-accent bg-accent/20 text-ink font-semibold shadow-sm'
                      : 'border-raised/60 bg-base/60 text-muted hover:text-ink hover:border-accent/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{tmpl.name}</span>
                    <span className="text-[10px] text-accent font-normal">{tmpl.format === 'shorts' ? '9:16' : '16:9'}</span>
                  </div>
                  <p className="text-[10px] text-muted line-clamp-1 mt-0.5">{tmpl.badge}</p>
                </button>
              )
            })}
          </div>
        </div>

        {/* --- Visual Range Trimmer & Monetization Badge --- */}
        <div className="rounded-lg border border-raised/60 bg-raised/30 p-3 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-1">
            <span className="text-xs font-semibold text-ink">Clip Boundaries & Trimmer</span>
            <span
              className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                end - start >= 60.0
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
              }`}
            >
              {end - start >= 60.0 ? '🟢 Monetized (>60s) · High RPM' : '🟡 Under 60s · Viral Hook'}
            </span>
          </div>

          {/* Time & Duration summary */}
          <div className="flex justify-between items-center text-xs text-muted">
            <span>
              Start: <strong className="text-ink font-mono">{formatTime(start)}</strong> ({start.toFixed(1)}s)
            </span>
            <span className="text-accent font-semibold">
              {(end - start).toFixed(1)}s total
            </span>
            <span>
              End: <strong className="text-ink font-mono">{formatTime(end)}</strong> ({end.toFixed(1)}s)
            </span>
          </div>

          {/* Visual Dual Sliders */}
          <div className="space-y-2">
            <div>
              <div className="flex justify-between text-[11px] text-muted mb-0.5">
                <span>Start Point (Drag left/right)</span>
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setStart((s) => Math.max(0, s - 5))}
                  >
                    -5s
                  </button>
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setStart((s) => Math.max(0, s - 1))}
                  >
                    -1s
                  </button>
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setStart((s) => Math.min(end - 3, s + 1))}
                  >
                    +1s
                  </button>
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setStart((s) => Math.min(end - 3, s + 5))}
                  >
                    +5s
                  </button>
                </div>
              </div>
              <input
                type="range"
                className="w-full accent-[#38BDF8] cursor-pointer"
                min={Math.max(0, clip.start_s - 120)}
                max={end - 3}
                step={0.5}
                value={start}
                onChange={(e) => setStart(Number(e.target.value))}
              />
            </div>

            <div>
              <div className="flex justify-between text-[11px] text-muted mb-0.5">
                <span>End Point (Drag left/right)</span>
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setEnd((e) => Math.max(start + 3, e - 5))}
                  >
                    -5s
                  </button>
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setEnd((e) => Math.max(start + 3, e - 1))}
                  >
                    -1s
                  </button>
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setEnd((e) => e + 1)}
                  >
                    +1s
                  </button>
                  <button
                    type="button"
                    className="px-1.5 py-0.5 rounded bg-raised text-[10px] hover:text-ink"
                    onClick={() => setEnd((e) => e + 5)}
                  >
                    +5s
                  </button>
                </div>
              </div>
              <input
                type="range"
                className="w-full accent-[#38BDF8] cursor-pointer"
                min={start + 3}
                max={clip.end_s + 120}
                step={0.5}
                value={end}
                onChange={(e) => setEnd(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="text-right">
            <button
              type="button"
              className="text-[11px] text-muted hover:text-ink underline"
              onClick={() => setShowExactNumbers(!showExactNumbers)}
            >
              {showExactNumbers ? 'Hide numeric seconds' : 'Type exact numeric seconds'}
            </button>
          </div>

          {showExactNumbers && (
            <div className="flex gap-3 pt-1 border-t border-raised/40">
              <div className="flex-1">
                <label className="label text-[11px]">Start (s)</label>
                <input
                  type="number"
                  className="input mt-0.5 text-xs !py-1"
                  value={start}
                  step={0.5}
                  onChange={(e) => setStart(Number(e.target.value))}
                />
              </div>
              <div className="flex-1">
                <label className="label text-[11px]">End (s)</label>
                <input
                  type="number"
                  className="input mt-0.5 text-xs !py-1"
                  value={end}
                  step={0.5}
                  onChange={(e) => setEnd(Number(e.target.value))}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap items-center">
        <button className="btn-accent" onClick={saveMetadata} disabled={busy !== null}>
          {busy === 'save' ? 'Saving…' : 'Save metadata'}
        </button>
        <button className="btn-ghost" onClick={rerender} disabled={busy !== null}>
          {busy === 'render' ? 'Queueing…' : 'Re-render'}
        </button>
        <input
          className="input !w-44"
          value={folder}
          onChange={(e) => {
            setFolder(e.target.value)
            setExportFolder(e.target.value)
          }}
          placeholder={t('export folder')}
          title={folder}
        />
        <button
          className="btn-ghost"
          onClick={async () => {
            const chosen = await pickExportFolder()
            if (chosen) setFolder(chosen)
          }}
          title={t('Choose where exported clips are saved')}
          aria-label={t('Choose export folder')}
        >
          <Folder />
        </button>
        <button className="btn-ghost" onClick={exportOne} disabled={busy !== null}>
          {busy === 'export' ? t('Exporting…') : t('Export')}
        </button>
        {/* Beside Export rather than only on the card in the grid: Export
            writes this one clip to a folder, and Publish is the same scope
            for the other destination. Only shown once a provider is set up,
            so the row does not carry a button that can only explain itself.
            Posting is not undoable, so it opens the confirm dialog rather
            than acting on the click, exactly like Publish all. */}
        {onPublish && (
          <button className="btn-ghost" onClick={onPublish} disabled={busy !== null}>
            {t('Publish ↗')}
          </button>
        )}
      </div>
      {notice && <p className="text-sm text-accent">{notice}</p>}
    </div>
  )
}
