import { NextRequest, NextResponse } from "next/server"

// Backend API URL - use Docker service name in container, localhost for local dev
const BACKEND_URL = process.env.VOICERA_BACKEND_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const response = await fetch(`${BACKEND_URL}/api/v1/outbound/call/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Forward the authorization header from the incoming request
        "Authorization": request.headers.get("Authorization") || "",
      },
      body: JSON.stringify(body),
    })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
