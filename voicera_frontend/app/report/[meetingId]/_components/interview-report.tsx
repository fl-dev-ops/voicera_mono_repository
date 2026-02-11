import type { CSSProperties } from "react"
import { Briefcase, Lightbulb, ThumbsUp } from "lucide-react"

export type CEFRLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2"

export interface AnalysisData {
  duration_seconds: number
  word_count: number
  sentence_count: number
  confidence_score: number
  cefr_level: CEFRLevel
  feedback_positive: string
  feedback_negative: string
}

interface PostInterviewReportProps {
  analysisData: AnalysisData
}

const JOB_MAPPING = {
  "A1-A2": {
    roles: [
      "Entry-Level Support",
      "Quality Analyst",
      "Relationship Officer",
      "Customer Service",
      "Data Entry",
    ],
    salary: "Less than ₹ 2.0 Lacs",
    theme: {
      bg: "bg-slate-50 dark:bg-slate-800/50",
      border: "border-slate-200 dark:border-slate-700",
      iconBg: "bg-teal-100 dark:bg-teal-900/30",
      iconColor: "text-teal-600 dark:text-teal-400",
      pillBorder: "border-slate-200 dark:border-slate-600",
      salaryBg: "bg-teal-600 dark:bg-teal-500",
    },
  },
  "B1-B2": {
    roles: [
      "Backend Executive",
      "Data Analysts",
      "Data Annotation",
      "Jr/IT Recruiter",
      "Process Associate",
    ],
    salary: "₹ 2.0 ~ 2.7 Lacs",
    theme: {
      bg: "bg-slate-50 dark:bg-slate-800/50",
      border: "border-slate-200 dark:border-slate-700",
      iconBg: "bg-teal-100 dark:bg-teal-900/30",
      iconColor: "text-teal-600 dark:text-teal-400",
      pillBorder: "border-slate-200 dark:border-slate-600",
      salaryBg: "bg-teal-600 dark:bg-teal-500",
    },
  },
  "C1-C2": {
    roles: [
      "Business Analyst",
      "Claim Associate",
      "Accounts AR/AP",
      "Title Search Executive",
      "Risk Analyst",
    ],
    salary: "More than ₹ 2.7 Lacs",
    theme: {
      bg: "bg-slate-50 dark:bg-slate-800/50",
      border: "border-slate-200 dark:border-slate-700",
      iconBg: "bg-teal-100 dark:bg-teal-900/30",
      iconColor: "text-teal-600 dark:text-teal-400",
      pillBorder: "border-slate-200 dark:border-slate-600",
      salaryBg: "bg-teal-600 dark:bg-teal-500",
    },
  },
} as const

function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.round(seconds % 60)

  if (hrs > 0) {
    return mins > 0 ? `${hrs}hr ${mins}min` : `${hrs}hr`
  }
  if (mins > 0) {
    return secs > 0 ? `${mins}min ${secs}s` : `${mins}min`
  }
  return `${secs}s`
}

function getDurationStatus(seconds: number): {
  status: "green" | "yellow" | "red"
  label: string
} {
  if (seconds >= 60 && seconds <= 120) {
    return { status: "green", label: "Perfect Timing" }
  }
  if ((seconds >= 30 && seconds < 60) || (seconds > 120 && seconds <= 180)) {
    return { status: "yellow", label: "Acceptable" }
  }
  return { status: "red", label: seconds < 30 ? "Too Short" : "Too Long" }
}

function getWordsPerMinuteStatus(
  wordCount: number,
  durationSeconds: number,
): { value: number; status: "green" | "yellow" | "red"; hint: string } {
  const wpm = durationSeconds > 0 ? (wordCount / durationSeconds) * 60 : 0
  const value = Math.round(wpm)

  if (wpm >= 120 && wpm <= 150) {
    return { value, status: "green", hint: "Perfect speaking pace" }
  }
  if ((wpm >= 100 && wpm < 120) || (wpm > 150 && wpm <= 170)) {
    return { value, status: "yellow", hint: "Aim for 120-150 WPM" }
  }
  return {
    value,
    status: "red",
    hint: wpm < 100 ? "Speaking too slow" : "Speaking too fast",
  }
}

function getJobGroup(level: CEFRLevel): "A1-A2" | "B1-B2" | "C1-C2" {
  if (level === "A1" || level === "A2") return "A1-A2"
  if (level === "B1" || level === "B2") return "B1-B2"
  return "C1-C2"
}

const STATUS_STYLES = {
  green: {
    bg: "bg-emerald-50 dark:bg-emerald-950/40",
    border: "border-emerald-200 dark:border-emerald-800",
    accent: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-400",
  },
  yellow: {
    bg: "bg-amber-50 dark:bg-amber-950/40",
    border: "border-amber-200 dark:border-amber-800",
    accent: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-400",
  },
  red: {
    bg: "bg-red-50 dark:bg-red-950/40",
    border: "border-red-200 dark:border-red-800",
    accent: "bg-red-500",
    text: "text-red-700 dark:text-red-400",
  },
} as const

function TalkTimeCard({ seconds }: { seconds: number }) {
  const { status, label } = getDurationStatus(seconds)
  const styles = STATUS_STYLES[status]

  return (
    <div
      className={`relative flex flex-col items-center justify-center overflow-hidden rounded-xl border p-4 text-center ${styles.bg} ${styles.border}`}
    >
      <div className={`absolute top-0 left-0 h-full w-1 ${styles.accent}`} />
      <span className="mb-1 text-xs font-semibold tracking-wider text-[var(--color-text-secondary)] uppercase">
        Talk Time
      </span>
      <span className="text-2xl font-bold text-[var(--color-text-primary)]">
        {formatDuration(seconds)}
      </span>
      <span className={`mt-1 text-xs font-medium ${styles.text}`}>
        {status === "green" && "✓ "}
        {label}
      </span>
    </div>
  )
}

function WordCountCard({ count }: { count: number }) {
  return (
    <div className="relative flex flex-col items-center justify-center overflow-hidden rounded-xl border border-blue-200 bg-blue-50 p-4 text-center dark:border-blue-800 dark:bg-blue-950/40">
      <div className="absolute top-0 left-0 h-full w-1 bg-blue-500" />
      <span className="mb-1 text-xs font-semibold tracking-wider text-[var(--color-text-secondary)] uppercase">
        Words
      </span>
      <span className="text-2xl font-bold text-[var(--color-text-primary)]">{count}</span>
      <span className="mt-1 text-xs font-medium text-blue-700 dark:text-blue-400">
        Words count
      </span>
    </div>
  )
}

function SentenceCountCard({ count }: { count: number }) {
  return (
    <div className="relative flex flex-col items-center justify-center overflow-hidden rounded-xl border border-violet-200 bg-violet-50 p-4 text-center dark:border-violet-800 dark:bg-violet-950/40">
      <div className="absolute top-0 left-0 h-full w-1 bg-violet-500" />
      <span className="mb-1 text-xs font-semibold tracking-wider text-[var(--color-text-secondary)] uppercase">
        Sentences
      </span>
      <span className="text-2xl font-bold text-[var(--color-text-primary)]">{count}</span>
      <span className="mt-1 text-xs font-medium text-violet-700 dark:text-violet-400">
        Total sentences spoken
      </span>
    </div>
  )
}

function WordsPerMinuteCard({
  wordCount,
  durationSeconds,
}: {
  wordCount: number
  durationSeconds: number
}) {
  const { value, status, hint } = getWordsPerMinuteStatus(wordCount, durationSeconds)
  const styles = STATUS_STYLES[status]

  return (
    <div
      className={`relative flex flex-col items-center justify-center overflow-hidden rounded-xl border p-4 text-center ${styles.bg} ${styles.border}`}
    >
      <div className={`absolute top-0 left-0 h-full w-1 ${styles.accent}`} />
      <span className="mb-1 text-xs font-semibold tracking-wider text-[var(--color-text-secondary)] uppercase">
        WPM
      </span>
      <span className="text-2xl font-bold text-[var(--color-text-primary)]">{value}</span>
      <span className={`mt-1 text-xs font-medium ${styles.text}`}>Words per Minute</span>
      <p className="mt-1 text-[10px] text-[var(--color-text-secondary)]">{hint}</p>
    </div>
  )
}

function ConfidenceGauge({ score }: { score: number }) {
  const normalizedScore = Math.max(0, Math.min(1, score))
  const percentage = Math.round(normalizedScore * 100)
  const strokeDashoffset = 126 * (1 - normalizedScore)

  return (
    <div className="flex flex-col items-center rounded-xl border border-slate-200 bg-[var(--color-bg-secondary)] p-4 dark:border-slate-700">
      <span className="mb-2 text-xs font-semibold tracking-wider text-[var(--color-text-secondary)] uppercase">
        Confidence
      </span>
      <div className="relative h-14 w-24 overflow-hidden">
        <svg className="h-full w-24 -translate-y-2 transform" viewBox="0 0 100 50">
          <path
            d="M 10 50 A 40 40 0 0 1 90 50"
            fill="none"
            className="stroke-slate-200 dark:stroke-slate-700"
            strokeWidth="10"
          />
          <path
            d="M 10 50 A 40 40 0 0 1 90 50"
            fill="none"
            className="stroke-emerald-500"
            strokeWidth="10"
            strokeDasharray="126"
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 1s ease-out" }}
          />
        </svg>
        <div className="absolute bottom-[10%] left-[2%] w-full text-center">
          <span className="text-xl font-bold text-[var(--color-text-primary)]">{percentage}%</span>
        </div>
      </div>
      <span className="mt-1 text-[10px] text-[var(--color-text-secondary)]">
        Voice Clarity Score
      </span>
    </div>
  )
}

function CEFRScale({ level }: { level: CEFRLevel }) {
  const levels: (CEFRLevel | "Pre-A1")[] = ["Pre-A1", "A1", "A2", "B1", "B2"]
  const activeIndex = levels.indexOf(level)

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Proficiency Level</h3>

      <div className="relative pt-[52px] pb-2">
        <div className="absolute top-[52px] right-0 left-0 h-2 rounded-full bg-slate-200 dark:bg-slate-700" />
        <div className="absolute top-[52px] left-[20%] h-2 w-[40%] rounded-l-full bg-teal-200/60 dark:bg-teal-800/40" />
        <div className="absolute top-[52px] left-[60%] h-2 w-[40%] rounded-r-full bg-teal-300/60 dark:bg-teal-700/40" />

        <div className="absolute top-[16%] right-0 left-0 grid grid-cols-5">
          {levels.map((l, index) => (
            <div key={`marker-${l}`} className="flex justify-center">
              <div
                className={`flex flex-col items-center transition-opacity duration-300 ${
                  index === activeIndex ? "opacity-100" : "pointer-events-none opacity-0"
                }`}
              >
                <div className="rounded bg-slate-800 px-2 py-1 text-[10px] font-bold text-white shadow-lg dark:bg-slate-100 dark:text-slate-900">
                  YOU
                </div>
                <div className="h-0 w-0 border-t-8 border-r-[6px] border-l-[6px] border-r-transparent border-l-transparent border-t-slate-800 dark:border-t-slate-100" />
                <div className="mt-0.5 h-4 w-4 rounded-full border-2 border-white bg-teal-500 shadow-md dark:border-slate-900" />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-5">
          {levels.map((l) => (
            <span
              key={`label-${l}`}
              className="text-center text-xs font-medium text-[var(--color-text-secondary)]"
            >
              {l}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function JobEligibilityCard({ level }: { level: CEFRLevel }) {
  const group = getJobGroup(level)
  const { roles, salary, theme } = JOB_MAPPING[group]

  return (
    <div
      className={`${theme.bg} ${theme.border} flex flex-col items-start gap-4 rounded-xl border p-5 md:flex-row md:items-center`}
    >
      <div className={`rounded-lg p-3 ${theme.iconBg}`}>
        <Briefcase className={`h-6 w-6 ${theme.iconColor}`} />
      </div>

      <div className="flex-1">
        <h4 className="mb-1 text-sm font-bold tracking-wide text-[var(--color-text-primary)] uppercase">
          Job Market Ready
        </h4>
        <p className="text-sm leading-snug text-[var(--color-text-secondary)]">
          Based on your <strong>{group}</strong> level, you are eligible for:
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {roles.map((role) => (
            <span
              key={role}
              className={`rounded border bg-white px-2 py-1 text-xs font-medium text-[var(--color-text-primary)] shadow-sm dark:bg-slate-800 ${theme.pillBorder}`}
            >
              {role}
            </span>
          ))}
        </div>
      </div>

      <div
        className={`${theme.salaryBg} rounded-lg px-3 py-2 text-xs font-bold whitespace-nowrap text-white shadow-sm`}
      >
        {salary}
      </div>
    </div>
  )
}

function parseFeedbackPoints(text: string): string[] {
  const points = text
    .split(/(?<=[.!?])\s+(?=[A-Z])|[•\-]\s*/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .slice(0, 3)
    .map((point) => {
      const words = point.split(/\s+/)
      if (words.length > 30) {
        return `${words.slice(0, 30).join(" ")}...`
      }
      return point
    })

  return points
}

function FeedbackSection({
  positive,
  negative,
}: {
  positive: string
  negative: string
}) {
  const positivePoints = parseFeedbackPoints(positive)
  const negativePoints = parseFeedbackPoints(negative)

  return (
    <div className="grid grid-cols-1 gap-6 border-t border-slate-200 pt-6 dark:border-slate-700 md:grid-cols-2">
      <div className="flex gap-3">
        <div className="mt-0.5 min-w-[24px]">
          <ThumbsUp className="h-5 w-5 text-emerald-500" />
        </div>
        <div>
          <h4 className="mb-2 text-xs font-bold text-[var(--color-text-primary)] uppercase">
            What went well
          </h4>
          <ul className="space-y-2">
            {positivePoints.map((point, index) => (
              <li
                key={index}
                className="flex gap-2 text-sm leading-relaxed text-[var(--color-text-secondary)]"
              >
                <span className="shrink-0 text-emerald-500">•</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="mt-0.5 min-w-[24px]">
          <Lightbulb className="h-5 w-5 text-amber-500" />
        </div>
        <div>
          <h4 className="mb-2 text-xs font-bold text-[var(--color-text-primary)] uppercase">
            What to improve
          </h4>
          <ul className="space-y-2">
            {negativePoints.map((point, index) => (
              <li
                key={index}
                className="flex gap-2 text-sm leading-relaxed text-[var(--color-text-secondary)]"
              >
                <span className="shrink-0 text-amber-500">•</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

export function InterviewReport({ analysisData }: PostInterviewReportProps) {
  const {
    duration_seconds,
    word_count,
    sentence_count,
    confidence_score,
    cefr_level,
    feedback_positive,
    feedback_negative,
  } = analysisData

  const insufficientData = word_count < 30

  return (
    <div
      className="mx-auto w-full max-w-4xl space-y-8 rounded-2xl border border-slate-100 bg-white p-4 shadow-lg sm:p-6 lg:p-8 dark:border-slate-800 dark:bg-slate-900"
      style={
        {
          "--color-bg-secondary": "#f8f9fb",
          "--color-text-primary": "#0f172a",
          "--color-text-secondary": "#475569",
        } as CSSProperties
      }
    >
      <div
        className={`grid grid-cols-1 gap-4 sm:gap-5 ${insufficientData ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}
      >
        <TalkTimeCard seconds={duration_seconds} />
        {!insufficientData && (
          <WordsPerMinuteCard wordCount={word_count} durationSeconds={duration_seconds} />
        )}
        <ConfidenceGauge score={confidence_score} />
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-5">
        <WordCountCard count={word_count} />
        <SentenceCountCard count={sentence_count} />
      </div>

      {!insufficientData ? (
        <>
          <div className="space-y-8">
            <CEFRScale level={cefr_level} />
            <JobEligibilityCard level={cefr_level} />
          </div>

          <FeedbackSection positive={feedback_positive} negative={feedback_negative} />
        </>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-6 text-center dark:border-slate-700 dark:bg-slate-800/50">
          <p className="text-sm text-[var(--color-text-secondary)]">
            Speak more to unlock detailed analysis — proficiency level, job eligibility, and
            personalized feedback require at least 30 words.
          </p>
        </div>
      )}
    </div>
  )
}
