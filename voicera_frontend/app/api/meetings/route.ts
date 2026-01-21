// app/api/meetings/route.ts
import { NextRequest, NextResponse } from "next/server"

import { SERVER_API_URL } from "@/lib/api-config"
const API_BASE_URL = SERVER_API_URL

// GET - Fetch meetings, optionally filtered by agent_type
export async function GET(request: NextRequest) {
  try {
    // Get the authorization header from the request
    const authHeader = request.headers.get("Authorization")
    
    if (!authHeader) {
      return NextResponse.json(
        { error: "Authorization header is required" },
        { status: 401 }
      )
    }

    // Get agent_type from query params (optional)
    const { searchParams } = new URL(request.url)
    const agentType = searchParams.get("agent_type")

    // Build the backend URL
    let backendUrl = `${API_BASE_URL}/api/v1/meetings`
    if (agentType) {
      backendUrl += `?agent_type=${encodeURIComponent(agentType)}`
    }

    // Forward the request to the backend
    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        "Accept": "application/json",
        "Authorization": authHeader,
      },
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    // Normalize _id to id if present (MongoDB returns _id)
    const normalizedData = Array.isArray(data)
      ? data.map((meeting: any) => ({
          ...meeting,
          id: meeting.id || meeting._id,
        }))
      : { ...data, id: data.id || data._id }

    return NextResponse.json(normalizedData)
  } catch (error) {
    console.error("Error fetching meetings:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
