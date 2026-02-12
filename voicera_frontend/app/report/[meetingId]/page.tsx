import { SERVER_API_URL } from "@/lib/api-config"
import { InterviewReport, type AnalysisData, type CEFRLevel } from "./_components/interview-report"

type EvaluationResponse = {
  scores: Record<string, number>
  overallScore: number
  performanceLevel?: string
  confidenceScore?: number
  cefrLevel?: string
  stats?: {
    sentences: number
    words: number
    talkTimeSeconds: number
  }
  whatDidGood?: string[]
  whatToImprove?: string[]
  sessionId?: string
  evaluatedAt?: string
  agentType?: string
}

async function getReport(meetingId: string): Promise<EvaluationResponse> {
  const res = await fetch(`${SERVER_API_URL}/api/v1/evaluation/${meetingId}`, {
    cache: "no-store",
  })

  if (!res.ok) {
    throw new Error(`Failed to fetch report (${res.status})`)
  }

  return res.json()
}

function normalizeCEFRLevel(level?: string): CEFRLevel {
  const upper = (level || "").toUpperCase()
  const direct = ["A1", "A2", "B1", "B2", "C1", "C2"] as const

  if (direct.includes(upper as CEFRLevel)) {
    return upper as CEFRLevel
  }

  if (upper.includes("A1")) return "A1"
  if (upper.includes("A2")) return "A2"
  if (upper.includes("B1")) return "B1"
  if (upper.includes("B2")) return "B2"
  if (upper.includes("C1")) return "C1"
  if (upper.includes("C2")) return "C2"

  return "A1"
}

function toAnalysisData(report: EvaluationResponse): AnalysisData {
  return {
    duration_seconds: report.stats?.talkTimeSeconds ?? 0,
    word_count: report.stats?.words ?? 0,
    sentence_count: report.stats?.sentences ?? 0,
    confidence_score: report.confidenceScore ?? 0,
    cefr_level: normalizeCEFRLevel(report.cefrLevel),
    feedback_positive: (report.whatDidGood || []).join(" "),
    feedback_negative: (report.whatToImprove || []).join(" "),
  }
}

export default async function ReportPage({
  params,
}: {
  params: Promise<{ meetingId: string }>
}) {
  const { meetingId } = await params
  const report = await getReport(meetingId)
  const analysisData = toAnalysisData(report)

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <h1 className="mb-8 text-center text-4xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        Session Analysis
      </h1>
      <InterviewReport analysisData={analysisData} />
    </main>
  )
}
