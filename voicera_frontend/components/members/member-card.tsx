"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  Loader2,
  Mail,
  Calendar,
  Trash2,
  MoreVertical,
  Crown,
  UserMinus,
} from "lucide-react"
import { Member } from "@/lib/api"

// Avatar color palette - deterministic based on name hash
const avatarColors = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-cyan-500",
  "bg-indigo-500",
  "bg-teal-500",
  "bg-orange-500",
  "bg-pink-500",
]

const getAvatarColor = (name: string): string => {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return avatarColors[Math.abs(hash) % avatarColors.length]
}

const getInitials = (name: string) => {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

interface MemberCardProps {
  member: Member
  isCurrentUser: boolean
  isDeleting: boolean
  onDelete: (member: Member) => void
}

export function MemberCard({ member, isCurrentUser, isDeleting, onDelete }: MemberCardProps) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const isOwner = member.is_owner === true
  const canDelete = !isCurrentUser && !isOwner
  const avatarColor = getAvatarColor(member.name)

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    setShowDeleteDialog(true)
  }

  const handleConfirmDelete = () => {
    setShowDeleteDialog(false)
    onDelete(member)
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div 
        className={`
          group relative bg-white rounded-2xl border overflow-hidden 
          shadow-md hover:shadow-lg transition-all duration-300
          ${isCurrentUser 
            ? "border-blue-300 ring-2 ring-blue-100" 
            : isOwner
            ? "border-amber-300"
            : "border-slate-200 hover:border-slate-300"
          }
        `}
      >
        {/* Owner indicator strip */}
        {isOwner && (
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-400 to-amber-500" />
        )}

        {/* Top Bar: Badges + Menu */}
        <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between">
          {/* Status badges */}
          <div className="flex items-center gap-1.5">
            {isOwner && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                <Crown className="h-3 w-3" />
                Owner
              </span>
            )}
            {isCurrentUser && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                You
              </span>
            )}
          </div>

          {/* Dropdown menu - shown on hover */}
          {canDelete && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  onClick={(e) => e.stopPropagation()}
                  className="h-8 w-8 rounded-lg bg-white/80 backdrop-blur-sm border border-slate-200/50 flex items-center justify-center shadow-sm opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  {isDeleting ? (
                    <Loader2 className="h-4 w-4 text-slate-500 animate-spin" />
                  ) : (
                    <MoreVertical className="h-4 w-4 text-slate-500" />
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem
                  onClick={handleDeleteClick}
                  className="cursor-pointer text-red-600 focus:text-red-600 focus:bg-red-50"
                  disabled={isDeleting}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Remove member
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Content */}
        <div className="p-5 pt-12 flex flex-col items-center text-center">
          {/* Avatar */}
          <div 
            className={`flex items-center justify-center h-16 w-16 rounded-full ${avatarColor} text-white font-semibold text-lg shadow-sm`}
          >
            {getInitials(member.name)}
          </div>

          {/* Name & Company */}
          <div className="mt-4 space-y-1">
            <h3 className="font-semibold text-base text-slate-900 leading-tight">
              {member.name}
            </h3>
            <p className="text-sm text-slate-500">
              {member.company_name}
            </p>
          </div>

          {/* Divider */}
          <div className="w-full border-t border-slate-100 my-4" />

          {/* Contact Info */}
          <div className="w-full space-y-2.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <a 
                  href={`mailto:${member.email}`}
                  className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
                >
                  <Mail className="h-4 w-4 shrink-0" />
                  <span className="truncate">{member.email}</span>
                </a>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>{member.email}</p>
              </TooltipContent>
            </Tooltip>
            
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Calendar className="h-4 w-4 shrink-0" />
              <span>Joined {formatDate(member.created_at)}</span>
            </div>
          </div>
        </div>

        {/* Delete Confirmation Dialog */}
        <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Remove Member</DialogTitle>
              <DialogDescription className="pt-2">
                Are you sure you want to remove <span className="font-medium text-slate-700">"{member.name}"</span>? 
                They will lose access to this organization.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="gap-2 sm:gap-1 w-full">
              <Button
                variant="outline"
                onClick={() => setShowDeleteDialog(false)}
                disabled={isDeleting}
                className="flex-1 sm:flex-none"
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="flex-1 sm:flex-none"
              >
                {isDeleting ? "Removing..." : "Remove"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  )
}