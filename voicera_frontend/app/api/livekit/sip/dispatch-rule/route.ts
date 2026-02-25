import { NextRequest, NextResponse } from "next/server"

const VOICE_SERVER_URL = process.env.VOICE_SERVER_URL || "http://localhost:7860"

/** POST /api/livekit/sip/dispatch-rule — create a dispatch rule (phone number → agent) */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const response = await fetch(`${VOICE_SERVER_URL}/livekit/sip/dispatch-rule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error("Error creating dispatch rule:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
