import { NextRequest, NextResponse } from "next/server"

const VOICE_SERVER_URL = process.env.VOICE_SERVER_URL || "http://localhost:7860"

/** DELETE /api/livekit/sip/dispatch-rule/[rule_id] — delete a dispatch rule */
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ rule_id: string }> }
) {
  try {
    const { rule_id } = await params
    const response = await fetch(
      `${VOICE_SERVER_URL}/livekit/sip/dispatch-rule/${encodeURIComponent(rule_id)}`,
      { method: "DELETE" }
    )
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error("Error deleting dispatch rule:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
