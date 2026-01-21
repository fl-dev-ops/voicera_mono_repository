"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { getCurrentUser, getAudiences, createAudience, getAudience, type User, type Audience, type CreateAudienceRequest } from "@/lib/api"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  ChevronRight,
  ChevronLeft,
  Plus,
  Search,
  MoreVertical,
  ArrowUpRight,
  Settings,
  Loader2,
  Phone,
} from "lucide-react"

// Helper function to get audience display name
const getAudienceDisplayName = (audience: Audience): string => {
  return audience.audience_name || "Unnamed Audience"
}

// Helper function to get audience description
const getAudienceDescription = (audience: Audience): string => {
  if (audience.phone_number) {
    return `Phone: ${audience.phone_number}`
  }
  if (audience.parameters) {
    const params = JSON.stringify(audience.parameters)
    return params.slice(0, 50) + (params.length > 50 ? "..." : "")
  }
  return "Audience"
}

interface AudienceFormData {
  audience_name: string
  phone_number: string
  parameters: string
}

const defaultFormData: AudienceFormData = {
  audience_name: "",
  phone_number: "",
  parameters: "",
}

export default function AudiencesPage() {
  const router = useRouter()
  const [audiences, setAudiences] = useState<Audience[]>([])
  const [searchQuery, setSearchQuery] = useState("")
  const [formData, setFormData] = useState<AudienceFormData>(defaultFormData)
  const [view, setView] = useState<"list" | "create">("list")
  const [user, setUser] = useState<User | null>(null)
  const [isLoadingAudiences, setIsLoadingAudiences] = useState(true)
  const [isCreatingAudience, setIsCreatingAudience] = useState(false)
  const [selectedAudience, setSelectedAudience] = useState<Audience | null>(null)
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false)
  const [isLoadingAudience, setIsLoadingAudience] = useState(false)

  // Fetch user data and audiences on mount
  useEffect(() => {
    async function fetchData() {
      try {
        const userData = await getCurrentUser()
        setUser(userData)
        
        // Fetch all audiences
        const audiencesData = await getAudiences()
        setAudiences(audiencesData)
      } catch (error) {
        console.error("Failed to fetch data:", error)
        router.push("/")
      } finally {
        setIsLoadingAudiences(false)
      }
    }
    fetchData()
  }, [router])

  // Filter audiences based on search
  const filteredAudiences = audiences.filter(
    (audience) => {
      const name = getAudienceDisplayName(audience).toLowerCase()
      const phone = audience.phone_number?.toLowerCase() || ""
      const query = searchQuery.toLowerCase()
      return name.includes(query) || phone.includes(query)
    }
  )

  const viewAudienceConfig = async (audience: Audience) => {
    setIsLoadingAudience(true)
    setIsViewDialogOpen(true)
    // Set the audience immediately so dialog can show
    setSelectedAudience(audience)
    try {
      const audienceData = await getAudience(audience.audience_name)
      setSelectedAudience(audienceData)
    } catch (error) {
      // Silently fall back to using the audience data from the list
      // This handles cases where the audience might not be found or there's a network error
      console.warn("Could not fetch fresh audience data, using cached data:", error instanceof Error ? error.message : error)
    } finally {
      setIsLoadingAudience(false)
    }
  }

  // Handle create new audience
  const handleCreateNew = () => {
    setFormData(defaultFormData)
    setView("create")
  }

  // Handle back to list
  const handleBackToList = () => {
    setView("list")
    setFormData(defaultFormData)
  }

  // Update form data helper
  const updateFormData = <K extends keyof AudienceFormData>(
    key: K,
    value: AudienceFormData[K]
  ) => {
    setFormData((prev) => ({ ...prev, [key]: value }))
  }

  // Handle save audience
  const handleSaveAudience = async () => {
    if (!formData.audience_name.trim()) {
      alert("Audience name is required")
      return
    }

    if (!formData.phone_number.trim()) {
      alert("Phone number is required")
      return
    }

    setIsCreatingAudience(true)

    try {
      let parameters: Record<string, any> | undefined = undefined
      if (formData.parameters.trim()) {
        try {
          parameters = JSON.parse(formData.parameters)
        } catch (e) {
          alert("Invalid JSON in parameters field")
          setIsCreatingAudience(false)
          return
        }
      }

      const audienceData: CreateAudienceRequest = {
        audience_name: formData.audience_name.trim(),
        phone_number: formData.phone_number.trim(),
        parameters: parameters,
      }

      // Create audience via API
      await createAudience(audienceData)
      
      // Refresh audiences list
      const audiencesData = await getAudiences()
      setAudiences(audiencesData)
      
      // Reset and go back to list
      handleBackToList()
    } catch (error) {
      console.error("Failed to create audience:", error)
      alert(error instanceof Error ? error.message : "Failed to create audience")
    } finally {
      setIsCreatingAudience(false)
    }
  }

  // Render list view
  if (view === "list") {
    return (
      <>
        <div className="flex flex-col h-screen bg-slate-50/50">
          {/* Header */}
          <header className="flex h-14 items-center gap-4 border-b border-slate-200 bg-white px-5 lg:px-8 sticky top-0 z-10">
            <nav className="flex items-center gap-1.5 text-sm">
              <span className="text-slate-500">Dashboard</span>
              <ChevronRight className="h-4 w-4 text-slate-400" />
              <span className="text-slate-900 font-medium">Audiences</span>
            </nav>
          </header>

          {/* Main Content */}
          <main className="flex-1 overflow-auto p-6 lg:p-8">
            {/* Greeting Section */}
            <div className="flex items-start justify-between mb-8">
              <div>
                <h1 className="text-3xl font-semibold text-slate-900 mb-1">Hi {user?.name}</h1>
                <p className="text-slate-500">Manage your audiences here.</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    type="text"
                    placeholder="Search Audience"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-10 pl-9 pr-4 w-64 rounded-lg border-slate-200 bg-white focus:border-slate-400 focus:ring-1 focus:ring-slate-200"
                  />
                </div>
              </div>
            </div>

            {/* Audience Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {/* Create New Audience Card */}
              <button
                onClick={handleCreateNew}
                className="cursor-pointer group relative border-2 border-dashed border-slate-300 rounded-xl p-6 h-64 flex flex-col items-center justify-center hover:border-slate-400 hover:bg-slate-50 transition-all duration-150"
              >
                <div className="h-12 w-12 rounded-full border-2 border-slate-300 flex items-center justify-center mb-3 group-hover:border-slate-400 transition-colors">
                  <Plus className="h-5 w-5 text-slate-400 group-hover:text-slate-600" />
                </div>
                <span className="text-sm font-medium text-slate-600 group-hover:text-slate-700">
                  Create New Audience
                </span>
              </button>

              {/* Loading State */}
              {isLoadingAudiences && (
                <div className="col-span-full text-center py-8 text-slate-500">
                  Loading audiences...
                </div>
              )}

              {/* Empty State */}
              {!isLoadingAudiences && filteredAudiences.length === 0 && (
                <div className="col-span-full text-center py-12">
                  <p className="text-slate-500 mb-2">No audiences found</p>
                  <p className="text-sm text-slate-400">Create your first audience to get started</p>
                </div>
              )}

              {/* Existing Audience Cards */}
              {!isLoadingAudiences && filteredAudiences.map((audience) => (
                <div
                  key={audience.audience_name}
                  className="relative bg-white rounded-xl border border-slate-200 p-5 h-64 flex flex-col hover:shadow-md hover:border-slate-300 transition-all duration-150"
                >
                  {/* Card Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="h-9 w-9 rounded-lg bg-slate-100 flex items-center justify-center">
                      <Phone className="h-4 w-4 text-slate-600" />
                    </div>
                    <button className="h-7 w-7 rounded hover:bg-slate-100 flex items-center justify-center transition-colors">
                      <MoreVertical className="h-4 w-4 text-slate-400" />
                    </button>
                  </div>

                  {/* Decorative Wave Pattern */}
                  <div className="flex-1 relative overflow-hidden mb-3">
                    <svg
                      className="absolute inset-0 w-full h-full"
                      viewBox="0 0 400 120"
                      preserveAspectRatio="none"
                    >
                      {[...Array(8)].map((_, i) => (
                        <path
                          key={i}
                          d={`M0,${60 + i * 4} Q100,${40 + i * 3} 200,${60 + i * 4} T400,${60 + i * 4}`}
                          fill="none"
                          stroke={`rgba(60, 70, 85, ${0.35 - i * 0.025})`}
                          strokeWidth="1.5"
                        />
                      ))}
                    </svg>
                  </div>

                  {/* Audience Info */}
                  <div className="mb-3">
                    <h3 className="text-base font-semibold text-slate-900 mb-0.5">{getAudienceDisplayName(audience)}</h3>
                    <p className="text-sm text-slate-500">{getAudienceDescription(audience)}</p>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2">
                    <Button
                      disabled
                      variant="outline"
                      className="flex-1 h-9 rounded-lg border-slate-200 text-slate-700 hover:bg-slate-50 gap-1.5 text-sm transition-colors"
                    >
                      <Phone className="h-3.5 w-3.5" />
                      Test
                    </Button>
                    <Button
                      onClick={() => viewAudienceConfig(audience)}
                      variant="outline"
                      className="cursor-pointer flex-1 h-9 rounded-lg border-slate-200 text-slate-700 hover:bg-slate-50 gap-1.5 text-sm transition-colors"
                    >
                      <Settings className="h-3.5 w-3.5" />
                      View
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </main>
        </div>

        {/* View Audience Dialog */}
        <Dialog open={isViewDialogOpen} onOpenChange={setIsViewDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Audience Details</DialogTitle>
              <DialogDescription>
                View audience information and configuration
              </DialogDescription>
            </DialogHeader>
            {isLoadingAudience ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : selectedAudience ? (
              <div className="space-y-4 mt-4">
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-700">Audience Name</label>
                  <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">{selectedAudience.audience_name}</p>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-700">Phone Number</label>
                  <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">{selectedAudience.phone_number}</p>
                </div>
                {selectedAudience.parameters && (
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">Parameters</label>
                    <pre className="text-xs text-slate-900 bg-slate-50 p-3 rounded-lg overflow-auto">
                      {JSON.stringify(selectedAudience.parameters, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ) : null}
          </DialogContent>
        </Dialog>
      </>
    )
  }

  // Render create view
  return (
    <div className="flex flex-col h-screen bg-slate-50/50">
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6 sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleBackToList}
            className="h-8 px-3 text-slate-600 hover:bg-slate-100 gap-1.5"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-semibold text-slate-900">Create Audience</h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-8">
        <div className="max-w-4xl">
          <div className="bg-white rounded-xl border border-slate-200 p-8">
            <div className="space-y-8">
              {/* Audience Name */}
              <div className="space-y-3">
                <label className="text-base font-bold text-slate-900">Audience Name *</label>
                <Input
                  value={formData.audience_name}
                  onChange={(e) => updateFormData("audience_name", e.target.value)}
                  placeholder="Enter audience name"
                  className="h-12 rounded-lg border-slate-200 bg-white text-base focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                />
                <p className="text-sm text-slate-500">
                  Give your audience a unique name to identify it.
                </p>
              </div>

              {/* Phone Number */}
              <div className="space-y-3">
                <label className="text-base font-bold text-slate-900">Phone Number *</label>
                <Input
                  value={formData.phone_number}
                  onChange={(e) => updateFormData("phone_number", e.target.value)}
                  placeholder="Enter phone number"
                  className="h-12 rounded-lg border-slate-200 bg-white text-base focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                />
                <p className="text-sm text-slate-500">
                  Enter the phone number for this audience.
                </p>
              </div>

              {/* Parameters */}
              <div className="space-y-3">
                <label className="text-base font-bold text-slate-900">Parameters</label>
                <Textarea
                  value={formData.parameters}
                  onChange={(e) => updateFormData("parameters", e.target.value)}
                  placeholder='Enter JSON data (e.g., {"key": "value"})'
                  className="min-h-[200px] rounded-lg border-slate-200 bg-white resize-none text-base focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all font-mono text-sm"
                />
                <p className="text-sm text-slate-500">
                  Optional JSON data for additional audience parameters.
                </p>
              </div>
            </div>

            <Button
              onClick={handleSaveAudience}
              disabled={isCreatingAudience || !formData.audience_name.trim() || !formData.phone_number.trim()}
              className="mt-8 h-11 px-6 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreatingAudience ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  Create Audience
                </>
              )}
            </Button>
          </div>
        </div>
      </main>
    </div>
  )
}
