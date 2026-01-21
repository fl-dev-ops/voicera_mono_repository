"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { getCurrentUser, getCampaigns, createCampaign, getCampaign, getAgents, type User, type Campaign, type CreateCampaignRequest, type Agent } from "@/lib/api"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
  CalendarIcon,
} from "lucide-react"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

// Helper function to get campaign display name
const getCampaignDisplayName = (campaign: Campaign): string => {
  return campaign.campaign_name || "Unnamed Campaign"
}

// Helper function to get campaign description
const getCampaignDescription = (campaign: Campaign): string => {
  if (campaign.campaign_information) {
    // Check if campaign_information contains start_date
    if (typeof campaign.campaign_information === 'object' && campaign.campaign_information.start_date) {
      try {
        const startDate = new Date(campaign.campaign_information.start_date)
        return `Starts: ${startDate.toLocaleDateString("en-US", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        })}`
      } catch (e) {
        // Fall through to other checks
      }
    }
    const info = JSON.stringify(campaign.campaign_information)
    return info.slice(0, 50) + (info.length > 50 ? "..." : "")
  }
  if (campaign.agent_type) {
    return `Agent: ${campaign.agent_type}`
  }
  return campaign.status || "Campaign"
}

interface CampaignFormData {
  campaign_name: string
  agent_type: string
  status: string
  start_date: Date | undefined
}

const defaultFormData: CampaignFormData = {
  campaign_name: "",
  agent_type: "",
  status: "active",
  start_date: undefined,
}

export default function CampaignsPage() {
  const router = useRouter()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [searchQuery, setSearchQuery] = useState("")
  const [formData, setFormData] = useState<CampaignFormData>(defaultFormData)
  const [view, setView] = useState<"list" | "create">("list")
  const [user, setUser] = useState<User | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoadingCampaigns, setIsLoadingCampaigns] = useState(true)
  const [isCreatingCampaign, setIsCreatingCampaign] = useState(false)
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false)
  const [isLoadingCampaign, setIsLoadingCampaign] = useState(false)
  const [datePickerOpen, setDatePickerOpen] = useState(false)

  // Fetch user data and campaigns on mount
  useEffect(() => {
    async function fetchData() {
      try {
        const userData = await getCurrentUser()
        setUser(userData)
        
        // Fetch campaigns for this org
        if (userData.org_id) {
          const campaignsData = await getCampaigns(userData.org_id)
          setCampaigns(campaignsData)
          
          // Also fetch agents for dropdown
          const agentsData = await getAgents(userData.org_id)
          setAgents(agentsData)
        }
      } catch (error) {
        console.error("Failed to fetch data:", error)
        router.push("/")
      } finally {
        setIsLoadingCampaigns(false)
      }
    }
    fetchData()
  }, [router])

  // Filter campaigns based on search
  const filteredCampaigns = campaigns.filter(
    (campaign) => {
      const name = getCampaignDisplayName(campaign).toLowerCase()
      const description = getCampaignDescription(campaign).toLowerCase()
      const query = searchQuery.toLowerCase()
      return name.includes(query) || description.includes(query)
    }
  )

  const viewCampaignConfig = async (campaign: Campaign) => {
    setIsLoadingCampaign(true)
    setIsViewDialogOpen(true)
    // Set the campaign immediately so dialog can show
    setSelectedCampaign(campaign)
    try {
      const campaignData = await getCampaign(campaign.campaign_name)
      setSelectedCampaign(campaignData)
    } catch (error) {
      // Silently fall back to using the campaign data from the list
      // This handles cases where the campaign might not be found or there's a network error
      console.warn("Could not fetch fresh campaign data, using cached data:", error instanceof Error ? error.message : error)
    } finally {
      setIsLoadingCampaign(false)
    }
  }

  // Handle create new campaign
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
  const updateFormData = <K extends keyof CampaignFormData>(
    key: K,
    value: CampaignFormData[K]
  ) => {
    setFormData((prev) => ({ ...prev, [key]: value }))
  }

  // Handle save campaign
  const handleSaveCampaign = async () => {
    if (!user?.org_id) {
      console.error("No org_id found")
      return
    }

    if (!formData.campaign_name.trim()) {
      alert("Campaign name is required")
      return
    }

    setIsCreatingCampaign(true)

    try {
      // Format start_date as ISO string if provided
      let campaignInformation: Record<string, any> | undefined = undefined
      if (formData.start_date) {
        campaignInformation = {
          start_date: formData.start_date.toISOString(),
        }
      }

      const campaignData: CreateCampaignRequest = {
        campaign_name: formData.campaign_name.trim(),
        org_id: user.org_id,
        agent_type: formData.agent_type || undefined,
        status: formData.status || "active",
        campaign_information: campaignInformation,
      }

      // Create campaign via API
      await createCampaign(campaignData)
      
      // Refresh campaigns list
      const campaignsData = await getCampaigns(user.org_id)
      setCampaigns(campaignsData)
      
      // Reset and go back to list
      handleBackToList()
    } catch (error) {
      console.error("Failed to create campaign:", error)
      alert(error instanceof Error ? error.message : "Failed to create campaign")
    } finally {
      setIsCreatingCampaign(false)
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
              <span className="text-slate-900 font-medium">Campaigns</span>
            </nav>
          </header>

          {/* Main Content */}
          <main className="flex-1 overflow-auto p-6 lg:p-8">
            {/* Greeting Section */}
            <div className="flex items-start justify-between mb-8">
              <div>
                <h1 className="text-3xl font-semibold text-slate-900 mb-1">Hi {user?.name}</h1>
                <p className="text-slate-500">Manage your campaigns here.</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    type="text"
                    placeholder="Search Campaign"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-10 pl-9 pr-4 w-64 rounded-lg border-slate-200 bg-white focus:border-slate-400 focus:ring-1 focus:ring-slate-200"
                  />
                </div>
              </div>
            </div>

            {/* Campaign Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {/* Create New Campaign Card */}
              <button
                onClick={handleCreateNew}
                className="cursor-pointer group relative border-2 border-dashed border-slate-300 rounded-xl p-6 h-64 flex flex-col items-center justify-center hover:border-slate-400 hover:bg-slate-50 transition-all duration-150"
              >
                <div className="h-12 w-12 rounded-full border-2 border-slate-300 flex items-center justify-center mb-3 group-hover:border-slate-400 transition-colors">
                  <Plus className="h-5 w-5 text-slate-400 group-hover:text-slate-600" />
                </div>
                <span className="text-sm font-medium text-slate-600 group-hover:text-slate-700">
                  Create New Campaign
                </span>
              </button>

              {/* Loading State */}
              {isLoadingCampaigns && (
                <div className="col-span-full text-center py-8 text-slate-500">
                  Loading campaigns...
                </div>
              )}

              {/* Empty State */}
              {!isLoadingCampaigns && filteredCampaigns.length === 0 && (
                <div className="col-span-full text-center py-12">
                  <p className="text-slate-500 mb-2">No campaigns found</p>
                  <p className="text-sm text-slate-400">Create your first campaign to get started</p>
                </div>
              )}

              {/* Existing Campaign Cards */}
              {!isLoadingCampaigns && filteredCampaigns.map((campaign) => (
                <div
                  key={campaign.campaign_name}
                  className="relative bg-white rounded-xl border border-slate-200 p-5 h-64 flex flex-col hover:shadow-md hover:border-slate-300 transition-all duration-150"
                >
                  {/* Card Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="h-9 w-9 rounded-lg bg-slate-100 flex items-center justify-center">
                      <ArrowUpRight className="h-4 w-4 text-slate-600" />
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

                  {/* Campaign Info */}
                  <div className="mb-3">
                    <h3 className="text-base font-semibold text-slate-900 mb-0.5">{getCampaignDisplayName(campaign)}</h3>
                    <p className="text-sm text-slate-500">{getCampaignDescription(campaign)}</p>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2">
                    <Button
                      disabled
                      variant="outline"
                      className="flex-1 h-9 rounded-lg border-slate-200 text-slate-700 hover:bg-slate-50 gap-1.5 text-sm transition-colors"
                    >
                      <Settings className="h-3.5 w-3.5" />
                      Test
                    </Button>
                    <Button
                      onClick={() => viewCampaignConfig(campaign)}
                      variant="outline"
                      className="cursor-pointer flex-1 h-9 rounded-lg border-slate-200 text-slate-700 hover:bg-slate-50 gap-1.5 text-sm transition-colors"
                    >
                      <Settings className="h-3.5 w-3.5" />
                      Config
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </main>
        </div>

        {/* View Campaign Dialog */}
        <Dialog open={isViewDialogOpen} onOpenChange={setIsViewDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Campaign Configuration</DialogTitle>
              <DialogDescription>
                View campaign details and configuration
              </DialogDescription>
            </DialogHeader>
            {isLoadingCampaign ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : selectedCampaign ? (
              <div className="space-y-4 mt-4">
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-700">Campaign Name</label>
                  <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">{selectedCampaign.campaign_name}</p>
                </div>
                {selectedCampaign.agent_type && (
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">Agent Type</label>
                    <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">{selectedCampaign.agent_type}</p>
                  </div>
                )}
                {selectedCampaign.status && (
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">Status</label>
                    <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">{selectedCampaign.status}</p>
                  </div>
                )}
                {selectedCampaign.org_id && (
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">Organization ID</label>
                    <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">{selectedCampaign.org_id}</p>
                  </div>
                )}
                {selectedCampaign.campaign_information && (
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">Campaign Start Date</label>
                    {typeof selectedCampaign.campaign_information === 'object' && 
                     selectedCampaign.campaign_information.start_date ? (
                      <p className="text-sm text-slate-900 bg-slate-50 p-3 rounded-lg">
                        {new Date(selectedCampaign.campaign_information.start_date).toLocaleDateString("en-US", {
                          day: "2-digit",
                          month: "long",
                          year: "numeric",
                        })}
                      </p>
                    ) : (
                      <pre className="text-xs text-slate-900 bg-slate-50 p-3 rounded-lg overflow-auto">
                        {JSON.stringify(selectedCampaign.campaign_information, null, 2)}
                      </pre>
                    )}
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
          <h1 className="text-sm font-semibold text-slate-900">Create Campaign</h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-8">
        <div className="max-w-4xl">
          <div className="bg-white rounded-xl border border-slate-200 p-8">
            <div className="grid grid-cols-2 gap-6 items-stretch">
              {/* Campaign Name */}
              <div className="flex flex-col space-y-3">
                <label className="text-base font-bold text-slate-900">Campaign Name *</label>
                <Input
                  value={formData.campaign_name}
                  onChange={(e) => updateFormData("campaign_name", e.target.value)}
                  placeholder="Enter campaign name"
                  className="h-12 rounded-lg border-slate-200 bg-white text-base focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                />
                <p className="text-sm text-slate-500 flex-1">
                  Give your campaign a unique name to identify it.
                </p>
              </div>

              {/* Start Date */}
              <div className="flex flex-col space-y-3">
                <label className="text-base font-bold text-slate-900">Campaign Start Date</label>
                <div className="relative">
                  <Popover open={datePickerOpen} onOpenChange={setDatePickerOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        className="w-full h-12 justify-start text-left font-normal rounded-lg border-slate-200 bg-white text-base hover:bg-slate-50 focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      >
                        <CalendarIcon className="mr-2 h-4 w-4 text-slate-400" />
                        {formData.start_date ? (
                          formData.start_date.toLocaleDateString("en-US", {
                            day: "2-digit",
                            month: "long",
                            year: "numeric",
                          })
                        ) : (
                          <span className="text-slate-500">Select start date</span>
                        )}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={formData.start_date}
                        onSelect={(date) => {
                          updateFormData("start_date", date)
                          setDatePickerOpen(false)
                        }}
                        disabled={(date) => date < new Date(new Date().setHours(0, 0, 0, 0))}
                        initialFocus
                      />
                    </PopoverContent>
                  </Popover>
                </div>
                <p className="text-sm text-slate-500 flex-1">
                  Select when the campaign should start. Past dates are not allowed.
                </p>
              </div>

              {/* Agent Type */}
              <div className="flex flex-col space-y-3">
                <label className="text-base font-bold text-slate-900">Agent Type</label>
                <Select 
                  value={formData.agent_type || undefined} 
                  onValueChange={(v) => updateFormData("agent_type", v === "__none__" ? "" : v)}
                >
                  <SelectTrigger className="h-12 rounded-lg border-slate-200 bg-white text-base font-medium hover:bg-slate-50 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all">
                    <SelectValue placeholder="Select agent type (optional)" />
                  </SelectTrigger>
                  <SelectContent className="rounded-lg">
                    <SelectItem value="__none__">None</SelectItem>
                    {Array.from(new Set(agents.map(a => a.agent_type))).map((agentType, index) => (
                      <SelectItem key={`agent-type-${agentType}-${index}`} value={agentType} className="py-2.5">
                        {agentType}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-sm text-slate-500 flex-1">
                  Select an agent type to associate with this campaign (optional).
                </p>
              </div>

              {/* Status */}
              <div className="flex flex-col space-y-3">
                <label className="text-base font-bold text-slate-900">Status</label>
                <Select value={formData.status} onValueChange={(v) => updateFormData("status", v)}>
                  <SelectTrigger className="h-12 rounded-lg border-slate-200 bg-white text-base font-medium hover:bg-slate-50 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all">
                    <SelectValue placeholder="Select status" />
                  </SelectTrigger>
                  <SelectContent className="rounded-lg">
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                    <SelectItem value="paused">Paused</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-sm text-slate-500 flex-1">
                  Set the status of this campaign.
                </p>
              </div>

              
            </div>

            <Button
              onClick={handleSaveCampaign}
              disabled={isCreatingCampaign || !formData.campaign_name.trim()}
              className="mt-8 h-11 px-6 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreatingCampaign ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  Create Campaign
                </>
              )}
            </Button>
          </div>
        </div>
      </main>
    </div>
  )
}

