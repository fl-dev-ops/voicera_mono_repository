import { NextRequest, NextResponse } from "next/server"

const VOICE_SERVER_URL = process.env.VOICE_SERVER_URL || "http://localhost:7860"

/** POST /api/livekit/sip/inbound-trunk — create a LiveKit SIP inbound trunk */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const response = await fetch(`${VOICE_SERVER_URL}/livekit/sip/inbound-trunk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error("Error creating inbound trunk:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
