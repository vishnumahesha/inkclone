import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    
    // Forward to existing FastAPI backend
    const backendUrl = 'http://127.0.0.1:8000/generate'
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      throw new Error(`Backend error: ${response.status}`)
    }
    
    const data = await response.json()
    return NextResponse.json(data)
    
  } catch (error) {
    console.error('API route error:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to generate document' },
      { status: 500 }
    )
  }
}
