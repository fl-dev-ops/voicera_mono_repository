import { SERVER_API_URL } from "@/lib/api-config"

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

export default async function ReportPage({
  params,
}: {
  params: Promise<{ meetingId: string }>
}) {
  const { meetingId } = await params
  const report = await getReport(meetingId)

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold">Evaluation Report</h1>
      <p className="mt-2 text-sm text-gray-600">Session: {report.sessionId || meetingId}</p>

      <section className="mt-6 rounded-xl border p-4">
        <p><strong>Overall Score:</strong> {report.overallScore}</p>
        <p><strong>Performance Level:</strong> {report.performanceLevel}</p>
        <p><strong>CEFR:</strong> {report.cefrLevel}</p>
        <p><strong>Confidence Score:</strong> {report.confidenceScore}</p>
      </section>

      <section className="mt-6 rounded-xl border p-4">
        <h2 className="font-medium">Scores</h2>
        <pre className="mt-2 overflow-auto text-sm">{JSON.stringify(report.scores, null, 2)}</pre>
      </section>

      <section className="mt-6 rounded-xl border p-4">
        <h2 className="font-medium">Stats</h2>
        <pre className="mt-2 overflow-auto text-sm">{JSON.stringify(report.stats, null, 2)}</pre>
      </section>

      <section className="mt-6 rounded-xl border p-4">
        <h2 className="font-medium">What You Did Good</h2>
        <ul className="mt-2 list-disc pl-5">
          {(report.whatDidGood || []).map((item, idx) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="mt-6 rounded-xl border p-4">
        <h2 className="font-medium">What To Improve</h2>
        <ul className="mt-2 list-disc pl-5">
          {(report.whatToImprove || []).map((item, idx) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="mt-6 rounded-xl border p-4">
        <h2 className="font-medium">Raw JSON</h2>
        <pre className="mt-2 overflow-auto text-xs">{JSON.stringify(report, null, 2)}</pre>
      </section>
    </main>
  )
}
