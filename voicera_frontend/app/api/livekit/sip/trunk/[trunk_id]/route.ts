import { NextRequest, NextResponse } from "next/server"

const VOICE_SERVER_URL = process.env.VOICE_SERVER_URL || "http://localhost:7860"

/** DELETE /api/livekit/sip/trunk/[trunk_id] — delete an inbound or outbound trunk */
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ trunk_id: string }> }
) {
  try {
    const { trunk_id } = await params
    const response = await fetch(
      `${VOICE_SERVER_URL}/livekit/sip/trunk/${encodeURIComponent(trunk_id)}`,
      { method: "DELETE" }
    )
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error("Error deleting trunk:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
