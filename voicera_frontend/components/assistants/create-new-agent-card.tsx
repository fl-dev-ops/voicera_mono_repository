"use client"

import { Plus } from "lucide-react"

interface CreateNewAgentCardProps {
  onCreateNew: () => void
}

export function CreateNewAgentCard({ onCreateNew }: CreateNewAgentCardProps) {
  return (
    <div
      onClick={onCreateNew}
      className="shadow-md cursor-pointer group relative bg-white rounded-2xl border border-dashed border-slate-300 overflow-hidden hover:shadow-lg hover:border-slate-400 transition-all duration-300"
      style={{ minHeight: "360px", minWidth: "0" }}
      tabIndex={0}
      role="button"
      aria-label="Create New Agent"
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onCreateNew()
        }
      }}
    >
      {/* Top Bar: Icon placement (empty for plus card) */}
      <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between">
        <div className="h-9 w-9 rounded-lg bg-white/80 backdrop-blur-sm border border-slate-200/50 flex items-center justify-center shadow-sm opacity-0" />
        <div className="h-9 w-9" />
      </div>

      {/* Wave Hero Section (grey - like placeholder) */}
      <div className="relative h-40 bg-gradient-to-br from-slate-50 via-white to-slate-50 overflow-hidden flex items-center justify-center">
        {/* Simple animated "pulse" ring for plus */}
        <div className="relative flex flex-col items-center justify-center w-full h-full">
          <span className="absolute inline-flex h-20 w-20 rounded-full bg-slate-200 opacity-30 animate-pulse" />
          <span className="inline-flex h-16 w-16 rounded-full border-4 border-slate-300 items-center justify-center bg-white z-10 group-hover:border-slate-400 transition-colors">
            <Plus className="h-7 w-7 text-slate-400 group-hover:text-slate-600 transition-colors" />
          </span>
        </div>
        {/* Subtle overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-white via-transparent to-transparent" />
      </div>

      {/* Content Section */}
      <div className="px-5 pb-5 -mt-2 flex flex-col h-[120px] items-center justify-center">
        <h3 className="text-lg font-semibold text-slate-900 mb-2 text-center">
          Create New Agent
        </h3>
        <p className="text-sm text-slate-500 text-center">
          Generate a new AI agent for your team
        </p>
      </div>
    </div>
  )
}
