import { NextResponse } from "next/server"
import { SERVER_API_URL } from "@/lib/api-config"

const API_BASE_URL = SERVER_API_URL

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ meetingId: string }> }
) {
  try {
    const { meetingId } = await params

    const response = await fetch(`${API_BASE_URL}/api/v1/evaluation/${meetingId}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    })

    const data = await response.json()
    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error("Error fetching public evaluation:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
