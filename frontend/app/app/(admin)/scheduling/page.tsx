"use client";

import { useState, useEffect, useRef } from "react";
import * as React from "react";
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isSameDay, addMonths, subMonths, startOfWeek, endOfWeek } from "date-fns";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import {
  getSchedulingCandidates,
  getCalComBookings,
  getCalComEventTypes,
  createCalComBooking,
  sendSchedulingEmails,
  syncCalComBookings,
  deleteCalComBooking,
  type SchedulingAssessment,
  type CalComBookingResponse,
  type CalComEventType,
  type SchedulingCandidate,
} from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Calendar as CalendarIcon, Mail, ExternalLink, RefreshCw, CheckCircle2, Clock, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

export default function SchedulingPage() {
  const { accessToken } = useSupabaseAuth();
  const queryClient = useQueryClient();
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [hoveredDate, setHoveredDate] = useState<Date | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null);
  const [expandedAssessments, setExpandedAssessments] = useState<Set<string>>(new Set());
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set());
  const [selectedEventType, setSelectedEventType] = useState<string>("");
  const [sendingEmails, setSendingEmails] = useState(false);
  
  // Use ref to track hovered element for scroll handler
  const hoveredElementRef = useRef<HTMLElement | null>(null);
  const hoveredDateRef = useRef<Date | null>(null);
  const hideTooltipTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // Set up scroll and click handlers to close tooltip
  useEffect(() => {
    const handleScroll = () => {
      // Close tooltip on scroll
      if (hoveredDate) {
        hoveredElementRef.current = null;
        hoveredDateRef.current = null;
        setHoveredDate(null);
        setTooltipPosition(null);
      }
    };
    
    const handleClickOutside = (e: MouseEvent) => {
      // Close tooltip if clicking outside of it
      if (hoveredDate) {
        const target = e.target as HTMLElement;
        const tooltip = document.querySelector('[data-tooltip-id]');
        const calendarCell = hoveredElementRef.current;
        
        // Check if click is outside both tooltip and calendar cell
        const isClickInTooltip = tooltip && (
          tooltip.contains(target) ||
          target.closest('[data-tooltip-id]') === tooltip
        );
        const isClickInCell = calendarCell && (
          calendarCell.contains(target) ||
          target.closest('.relative') === calendarCell
        );
        
        if (!isClickInTooltip && !isClickInCell) {
          hoveredElementRef.current = null;
          hoveredDateRef.current = null;
          setHoveredDate(null);
          setTooltipPosition(null);
        }
      }
    };
    
    window.addEventListener("scroll", handleScroll, { passive: true });
    document.addEventListener("click", handleClickOutside, true);
    
    return () => {
      window.removeEventListener("scroll", handleScroll);
      document.removeEventListener("click", handleClickOutside, true);
      if (hideTooltipTimeoutRef.current) {
        clearTimeout(hideTooltipTimeoutRef.current);
      }
    };
  }, [hoveredDate]);

  // Fetch candidates
  const { data: assessments, isLoading: candidatesLoading } = useQuery({
    queryKey: ["scheduling-candidates"],
    queryFn: () => getSchedulingCandidates({ accessToken: accessToken ?? undefined }),
    enabled: !!accessToken,
  });

  // Fetch bookings with polling to refresh status
  const { data: bookings, isLoading: bookingsLoading, refetch: refetchBookings } = useQuery({
    queryKey: ["cal-com-bookings"],
    queryFn: () => getCalComBookings({ accessToken: accessToken ?? undefined }),
    enabled: !!accessToken,
    refetchInterval: 60000, // Poll every 60 seconds to check for status updates
  });

  // Fetch event types
  const { data: eventTypes, isLoading: eventTypesLoading, error: eventTypesError } = useQuery({
    queryKey: ["cal-com-event-types"],
    queryFn: () => getCalComEventTypes({ accessToken: accessToken ?? undefined }),
    enabled: !!accessToken,
    retry: false, // Don't retry on error to avoid spam
  });

  // Get top 3 candidates per assessment (or all if expanded)
  const getCandidatesToShow = (assessment: SchedulingAssessment) => {
    if (expandedAssessments.has(assessment.assessmentId)) {
      return assessment.candidates;
    }
    return assessment.candidates.slice(0, 3);
  };

  const toggleAssessment = (assessmentId: string) => {
    setExpandedAssessments((prev) => {
      const next = new Set(prev);
      if (next.has(assessmentId)) {
        next.delete(assessmentId);
      } else {
        next.add(assessmentId);
      }
      return next;
    });
  };

  const toggleCandidate = (invitationId: string) => {
    setSelectedCandidates((prev) => {
      const next = new Set(prev);
      if (next.has(invitationId)) {
        next.delete(invitationId);
      } else {
        next.add(invitationId);
      }
      return next;
    });
  };

  // Calendar helpers
  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const calendarStart = startOfWeek(monthStart);
  const calendarEnd = endOfWeek(monthEnd);
  const calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd });

  // Get bookings for a specific date
  const getBookingsForDate = (date: Date): CalComBookingResponse[] => {
    if (!bookings) return [];
    return bookings.filter((booking) => {
      if (!booking.startTime) return false;
      const bookingDate = new Date(booking.startTime);
      return isSameDay(bookingDate, date);
    });
  };

  // Get booking status color
  const getBookingStatusColor = (status: string | null | undefined): string => {
    if (!status) return "bg-gray-400";
    const statusLower = status.toLowerCase();
    if (statusLower === "confirmed" || statusLower === "accepted") {
      return "bg-green-500";
    } else if (statusLower === "pending" || statusLower === "waiting") {
      return "bg-yellow-500";
    } else if (statusLower === "cancelled" || statusLower === "rejected") {
      return "bg-red-500";
    }
    return "bg-blue-500";
  };

  // Get booking status badge
  const getBookingStatusBadge = (status: string | null | undefined) => {
    if (!status) return null;
    const statusLower = status.toLowerCase();
    if (statusLower === "confirmed" || statusLower === "accepted") {
      return <Badge className="bg-green-50 text-green-700 border-green-200"><CheckCircle2 className="h-3 w-3 mr-1" />Confirmed</Badge>;
    } else if (statusLower === "pending" || statusLower === "waiting") {
      return <Badge className="bg-yellow-50 text-yellow-700 border-yellow-200"><Clock className="h-3 w-3 mr-1" />Pending</Badge>;
    } else if (statusLower === "cancelled" || statusLower === "rejected") {
      return <Badge className="bg-red-50 text-red-700 border-red-200">Cancelled</Badge>;
    }
    return <Badge>{status}</Badge>;
  };

  // Sync bookings manually
  const [syncingBookings, setSyncingBookings] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  const handleSyncBookings = async () => {
    if (!accessToken) return;
    setSyncingBookings(true);
    setSyncResult(null);
    try {
      const result = await syncCalComBookings({ accessToken: accessToken ?? undefined });
      setSyncResult(`Synced ${result.updated} of ${result.total} bookings. ${result.errors > 0 ? `${result.errors} errors.` : ""}`);
      // Refresh bookings after sync
      await refetchBookings();
      await queryClient.invalidateQueries({ queryKey: ["scheduling-candidates"] });
    } catch (error: any) {
      console.error("Failed to sync bookings:", error);
      setSyncResult("Failed to sync bookings. Please try again.");
    } finally {
      setSyncingBookings(false);
    }
  };

  // Delete booking
  const [deletingBookingId, setDeletingBookingId] = useState<string | null>(null);

  const handleDeleteBooking = async (booking: CalComBookingResponse) => {
    if (!accessToken) return;
    
    // Confirm deletion
    if (!confirm(`Are you sure you want to delete this booking?\n\n${booking.title || "Meeting"}\n${booking.startTime ? format(new Date(booking.startTime), "MMMM d, yyyy 'at' h:mm a") : ""}`)) {
      return;
    }

    setDeletingBookingId(booking.id);
    try {
      await deleteCalComBooking(booking.id, { accessToken: accessToken ?? undefined });
      
      // Refresh bookings and candidates after deletion
      await refetchBookings();
      await queryClient.invalidateQueries({ queryKey: ["scheduling-candidates"] });
      
      // Hide tooltip if this was the hovered booking
      if (hoveredDate) {
        const remainingBookings = getBookingsForDate(hoveredDate).filter(b => b.id !== booking.id);
        if (remainingBookings.length === 0) {
          setHoveredDate(null);
          setTooltipPosition(null);
        }
      }
    } catch (error: any) {
      console.error("Failed to delete booking:", error);
      alert(`Failed to delete booking: ${error.message || "Unknown error"}`);
    } finally {
      setDeletingBookingId(null);
    }
  };

  // Create booking for selected candidates
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [creatingBooking, setCreatingBooking] = useState(false);

  const handleCreateBooking = async () => {
    if (!selectedEventType || selectedCandidates.size === 0) return;
    if (!accessToken) return;

    setBookingError(null);
    setCreatingBooking(true);

    try {
      const candidateList = Array.from(selectedCandidates);
      const firstCandidate = assessments
        ?.flatMap((a) => a.candidates)
        .find((c) => c.invitationId === candidateList[0]);

      if (!firstCandidate) {
        setBookingError("Candidate not found");
        return;
      }

      // Don't send start_time - let Cal.com generate a booking link for candidate to choose their own time
      const booking = await createCalComBooking(
        {
          invitationId: firstCandidate.invitationId,
          eventTypeId: selectedEventType,
          // Don't send startTime - this creates a booking link instead of a specific booking
        },
        { accessToken: accessToken ?? undefined },
      );

      // Show success message
      if (booking.bookingUrl) {
        alert(`Booking link created successfully!\n\nShare this link with candidates:\n${booking.bookingUrl}`);
      } else {
        alert("Booking created successfully!");
      }

      // Refresh bookings and candidates to show the new booking
      await queryClient.invalidateQueries({ queryKey: ["cal-com-bookings"] });
      await queryClient.invalidateQueries({ queryKey: ["scheduling-candidates"] });
    } catch (error: any) {
      console.error("Failed to create booking:", error);
      
      // Extract user-friendly error message
      let errorMessage = "Failed to create booking. ";
      
      if (error?.detail) {
        try {
          const detail = typeof error.detail === 'string' ? JSON.parse(error.detail) : error.detail;
          if (detail.detail) {
            const calError = typeof detail.detail === 'string' ? JSON.parse(detail.detail) : detail.detail;
            if (calError.message) {
              errorMessage += calError.message;
            } else {
              errorMessage += detail.detail;
            }
          } else {
            errorMessage += detail;
          }
        } catch {
          errorMessage += error.detail || "Unknown error occurred";
        }
      } else if (error?.message) {
        errorMessage += error.message;
      } else {
        errorMessage += "Please check Cal.com configuration and try again.";
      }

      setBookingError(errorMessage);
    } finally {
      setCreatingBooking(false);
    }
  };

  // Send scheduling emails
  const [emailError, setEmailError] = useState<string | null>(null);

  const handleSendEmails = async () => {
    if (selectedCandidates.size === 0) return;
    if (!accessToken) return;

    setEmailError(null);
    setSendingEmails(true);

    try {
      // Get booking URL for selected candidates
      const candidateList = Array.from(selectedCandidates);
      const firstCandidate = assessments
        ?.flatMap((a) => a.candidates)
        .find((c) => c.invitationId === candidateList[0]);

      if (!firstCandidate?.booking?.bookingUrl) {
        setEmailError("Please create a booking link first for at least one candidate.");
        return;
      }

      const result = await sendSchedulingEmails(
        {
          invitationIds: candidateList,
          bookingUrl: firstCandidate.booking.bookingUrl,
        },
        { accessToken: accessToken ?? undefined },
      );

      if (result.failed > 0) {
        setEmailError(
          `Sent ${result.sent} email(s) successfully, but ${result.failed} failed. ${result.errors.join("; ")}`
        );
      } else {
        alert(`✅ Successfully sent ${result.sent} email(s) with booking links!`);
        // Clear error on success
        setEmailError(null);
        // Refresh candidates to show updated booking status
        await queryClient.invalidateQueries({ queryKey: ["scheduling-candidates"] });
      }

      if (result.errors.length > 0) {
        console.error("Email errors:", result.errors);
      }
    } catch (error: any) {
      console.error("Failed to send emails:", error);
      let errorMessage = "Failed to send emails. ";
      
      if (error?.detail) {
        try {
          const detail = typeof error.detail === 'string' ? JSON.parse(error.detail) : error.detail;
          errorMessage += typeof detail === 'string' ? detail : JSON.stringify(detail);
        } catch {
          errorMessage += error.detail || "Unknown error occurred";
        }
      } else if (error?.message) {
        errorMessage += error.message;
      } else {
        errorMessage += "Please check your email configuration.";
      }
      
      setEmailError(errorMessage);
    } finally {
      setSendingEmails(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Scheduling</h1>
        <p className="text-sm text-zinc-500">Schedule meetings with candidates and send booking links</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Calendar View */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Calendar</CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSyncBookings}
                    disabled={syncingBookings}
                    title="Sync booking statuses from Cal.com"
                  >
                    <RefreshCw className={`h-4 w-4 ${syncingBookings ? "animate-spin" : ""}`} />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm font-medium min-w-[120px] text-center">
                    {format(currentMonth, "MMMM yyyy")}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              {syncResult && (
                <div className={`mt-2 text-xs ${syncResult.includes("Failed") ? "text-red-600" : "text-green-600"}`}>
                  {syncResult}
                </div>
              )}
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-7 gap-1 mb-2">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
                  <div key={day} className="text-center text-xs font-medium text-zinc-500 p-2">
                    {day}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {calendarDays.map((day, idx) => {
                  const isCurrentMonth = isSameMonth(day, currentMonth);
                  const isToday = isSameDay(day, new Date());
                  const isSelected = selectedDate && isSameDay(day, selectedDate);
                  const dayBookings = getBookingsForDate(day);

                  return (
                    <div
                      key={idx}
                      className="relative"
                      ref={(el) => {
                        // Store element reference for scroll handler
                        if (el) {
                          (el as any)._dayElement = day;
                        }
                      }}
                      onMouseEnter={(e) => {
                        if (dayBookings.length > 0) {
                          const element = e.currentTarget as HTMLElement;
                          
                          // Check if element still exists
                          if (!element || !element.getBoundingClientRect) {
                            return;
                          }
                          
                          const updatePosition = () => {
                            // Check if element still exists
                            if (!element || !element.getBoundingClientRect) {
                              return;
                            }
                            
                            const rect = element.getBoundingClientRect();
                            const viewportWidth = window.innerWidth;
                            const viewportHeight = window.innerHeight;
                            
                            // Calculate tooltip position - appear to the left
                            const tooltipWidth = 320; // max-w-[320px]
                            const tooltipHeight = 200; // estimated height
                            
                            // Position to the left of the calendar cell (using getBoundingClientRect which accounts for scroll)
                            let x = rect.left - tooltipWidth - 10; // 10px gap from the cell
                            let y = rect.top; // getBoundingClientRect already accounts for scroll
                            
                            // Adjust if tooltip would go off screen on the left
                            if (x < 10) {
                              // Show on the right side instead
                              x = rect.right + 10;
                            }
                            
                            // Adjust vertical position to keep within viewport
                            if (y < 10) {
                              // Too close to top, adjust down
                              y = 10;
                            } else if (y + tooltipHeight > viewportHeight - 10) {
                              // Too close to bottom, adjust up
                              y = viewportHeight - tooltipHeight - 10;
                            }
                            
                            setTooltipPosition({ x, y });
                          };
                          
                          // Store element and date in refs for scroll handler
                          hoveredElementRef.current = element;
                          hoveredDateRef.current = day;
                          
                          updatePosition();
                          setHoveredDate(day);
                        }
                      }}
                      onMouseLeave={(e) => {
                        // Clear any existing timeout
                        if (hideTooltipTimeoutRef.current) {
                          clearTimeout(hideTooltipTimeoutRef.current);
                        }
                        
                        // Don't hide immediately - give time to move to tooltip
                        // Use a delay to allow mouse to move to tooltip
                        hideTooltipTimeoutRef.current = setTimeout(() => {
                          // Check if tooltip is still visible (if mouse is over it, onMouseEnter will have fired)
                          const tooltipElement = document.querySelector('[data-tooltip-id]') as HTMLElement;
                          if (!tooltipElement) {
                            // Tooltip is gone, so hide it
                            hoveredElementRef.current = null;
                            hoveredDateRef.current = null;
                            setHoveredDate(null);
                            setTooltipPosition(null);
                          }
                          // If tooltip still exists, it means mouse is over it, so keep it open
                        }, 50);
                      }}
                    >
                      <button
                        onClick={() => setSelectedDate(day)}
                        className={cn(
                          "aspect-square p-2 text-sm rounded-lg border transition-colors w-full",
                          !isCurrentMonth && "text-zinc-300",
                          isCurrentMonth && "text-zinc-900",
                          isToday && "border-blue-500 bg-blue-50",
                          isSelected && "border-blue-600 bg-blue-100",
                          !isSelected && !isToday && "border-zinc-200 hover:bg-zinc-50",
                        )}
                      >
                        <div className="flex flex-col items-center gap-1">
                          <span>{format(day, "d")}</span>
                          {dayBookings.length > 0 && (
                            <div className="flex gap-1">
                              {dayBookings.slice(0, 3).map((booking) => (
                                <div
                                  key={booking.id}
                                  className={`w-1.5 h-1.5 rounded-full ${getBookingStatusColor(booking.status)}`}
                                />
                              ))}
                              {dayBookings.length > 3 && (
                                <span className="text-xs text-zinc-500">+{dayBookings.length - 3}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </button>
                    </div>
                  );
                })}
              </div>
            </CardContent>
            
            {/* Hover Tooltip */}
            {hoveredDate && tooltipPosition && getBookingsForDate(hoveredDate).length > 0 && (
              <div
                data-tooltip-id="booking-tooltip"
                className="fixed z-50 bg-white border border-zinc-200 rounded-lg shadow-xl p-3 min-w-[280px] max-w-[320px] animate-in fade-in-0 zoom-in-95 duration-200 pointer-events-auto"
                style={{
                  left: `${tooltipPosition.x}px`,
                  top: `${tooltipPosition.y}px`,
                }}
                onMouseEnter={(e) => {
                  // Cancel any pending hide timeout immediately
                  if (hideTooltipTimeoutRef.current) {
                    clearTimeout(hideTooltipTimeoutRef.current);
                    hideTooltipTimeoutRef.current = null;
                  }
                  
                  // Keep tooltip visible when hovering over it
                  // Make sure refs are still set
                  if (hoveredDate) {
                    hoveredDateRef.current = hoveredDate;
                  }
                }}
                onMouseLeave={(e) => {
                  // Clear any existing timeout
                  if (hideTooltipTimeoutRef.current) {
                    clearTimeout(hideTooltipTimeoutRef.current);
                  }
                  
                  // Use a delay before hiding in case mouse is moving back to calendar cell
                  hideTooltipTimeoutRef.current = setTimeout(() => {
                    // Check if mouse moved back to the calendar cell
                    const calendarCell = hoveredElementRef.current;
                    if (!calendarCell) {
                      hoveredElementRef.current = null;
                      hoveredDateRef.current = null;
                      setHoveredDate(null);
                      setTooltipPosition(null);
                      return;
                    }
                    
                    // Check if mouse is over the calendar cell or tooltip
                    const elementAtPoint = document.elementFromPoint(
                      e.clientX || window.innerWidth / 2,
                      e.clientY || window.innerHeight / 2
                    );
                    
                    const isOverCell = elementAtPoint && (
                      calendarCell.contains(elementAtPoint) ||
                      elementAtPoint.closest('.relative') === calendarCell
                    );
                    
                    const isOverTooltip = elementAtPoint && elementAtPoint.closest('[data-tooltip-id]');
                    
                    if (!isOverCell && !isOverTooltip) {
                      hoveredElementRef.current = null;
                      hoveredDateRef.current = null;
                      setHoveredDate(null);
                      setTooltipPosition(null);
                    }
                  }, 50);
                }}
              >
                <h3 className="text-sm font-semibold mb-2 text-zinc-900 border-b border-zinc-200 pb-2">
                  {format(hoveredDate, "MMMM d, yyyy")}
                </h3>
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {getBookingsForDate(hoveredDate).map((booking) => (
                    <div
                      key={booking.id}
                      className="flex items-start justify-between gap-2 p-2 bg-zinc-50 rounded text-sm hover:bg-zinc-100 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <p className="font-medium text-zinc-900 truncate">{booking.title || "Meeting"}</p>
                          {getBookingStatusBadge(booking.status)}
                        </div>
                        {booking.startTime && (
                          <p className="text-zinc-600 text-xs">
                            {format(new Date(booking.startTime), "h:mm a")}
                            {booking.endTime && (
                              <> - {format(new Date(booking.endTime), "h:mm a")}</>
                            )}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0 pointer-events-auto">
                        {booking.bookingUrl && (
                          <a
                            href={booking.bookingUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-700 transition-colors p-1 rounded hover:bg-blue-50"
                            onClick={(e) => e.stopPropagation()}
                            title="Open in Cal.com"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteBooking(booking);
                          }}
                          disabled={deletingBookingId === booking.id}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50 transition-colors p-1 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                          title="Delete booking"
                        >
                          {deletingBookingId === booking.id ? (
                            <RefreshCw className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                {/* Tooltip arrow pointing to the right (towards the calendar cell) */}
                <div
                  className="absolute top-4 -right-2 w-0 h-0 border-t-4 border-b-4 border-l-4 border-transparent border-l-zinc-200"
                />
                <div
                  className="absolute top-4 -right-[7px] w-0 h-0 border-t-4 border-b-4 border-l-4 border-transparent border-l-white"
                />
              </div>
            )}
          </Card>
        </div>

        {/* Candidates List and Actions */}
        <div className="lg:col-span-1 space-y-6">
          {/* Candidates List */}
          <Card>
            <CardHeader>
              <CardTitle>Candidates</CardTitle>
              <CardDescription>Top candidates by assessment</CardDescription>
            </CardHeader>
            <CardContent>
              {candidatesLoading ? (
                <p className="text-sm text-zinc-500">Loading candidates...</p>
              ) : !assessments || assessments.length === 0 ? (
                <p className="text-sm text-zinc-500">No candidates available</p>
              ) : (
                <div className="space-y-4 max-h-[600px] overflow-y-auto">
                  {assessments.map((assessment) => {
                    const candidatesToShow = getCandidatesToShow(assessment);
                    const isExpanded = expandedAssessments.has(assessment.assessmentId);
                    const hasMore = assessment.candidates.length > 3;

                    return (
                      <div key={assessment.assessmentId} className="border-b pb-4 last:border-0">
                        <button
                          onClick={() => toggleAssessment(assessment.assessmentId)}
                          className="flex items-center justify-between w-full mb-2 text-left"
                        >
                          <h3 className="font-medium text-sm">{assessment.assessmentTitle}</h3>
                          {hasMore && (
                            <span className="text-xs text-zinc-500">
                              {isExpanded ? (
                                <ChevronUp className="h-4 w-4" />
                              ) : (
                                <ChevronDown className="h-4 w-4" />
                              )}
                            </span>
                          )}
                        </button>
                        <div className="space-y-2">
                          {candidatesToShow.map((candidate) => {
                            const isSelected = selectedCandidates.has(candidate.invitationId);
                            return (
                              <div
                                key={candidate.invitationId}
                                className={cn(
                                  "p-2 rounded border cursor-pointer transition-colors",
                                  isSelected ? "border-blue-500 bg-blue-50" : "border-zinc-200 hover:bg-zinc-50",
                                )}
                                onClick={() => toggleCandidate(candidate.invitationId)}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate">{candidate.candidateName}</p>
                                    <p className="text-xs text-zinc-500 truncate">{candidate.candidateEmail}</p>
                                    {candidate.booking && (
                                      <div className="mt-1">
                                        {getBookingStatusBadge(candidate.booking.status)}
                                      </div>
                                    )}
                                  </div>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => toggleCandidate(candidate.invitationId)}
                                    className="mt-1"
                                  />
                                </div>
                              </div>
                            );
                          })}
                          {!isExpanded && hasMore && (
                            <p className="text-xs text-zinc-500 text-center">
                              +{assessment.candidates.length - 3} more
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Actions */}
          {selectedCandidates.size > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Actions</CardTitle>
                <CardDescription>
                  {selectedCandidates.size} candidate{selectedCandidates.size > 1 ? "s" : ""} selected
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Event Type</label>
                  {eventTypesLoading ? (
                    <p className="text-sm text-zinc-500">Loading event types...</p>
                  ) : eventTypesError ? (
                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-md">
                      <p className="text-sm font-medium text-amber-800 mb-1">
                        Cal.com API Key Not Configured
                      </p>
                      <p className="text-xs text-amber-700">
                        Please add <code className="bg-amber-100 px-1 rounded">CAL_COM_API_KEY</code> to your backend environment variables and restart the server.
                      </p>
                      <p className="text-xs text-amber-600 mt-2">
                        See <code className="bg-amber-100 px-1 rounded">docs/cal-com-setup.md</code> for setup instructions.
                      </p>
                    </div>
                  ) : !eventTypes || eventTypes.length === 0 ? (
                    <p className="text-sm text-amber-600">
                      No event types found. Please create event types in Cal.com or configure your API key.
                    </p>
                  ) : (
                    <select
                      value={selectedEventType}
                      onChange={(e) => setSelectedEventType(e.target.value)}
                      className="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm"
                    >
                      <option value="">Select event type...</option>
                      {eventTypes
                        .filter((et) => !et.hidden)
                        .map((et) => (
                          <option key={et.id} value={et.id}>
                            {et.title} {et.length ? `(${et.length} min)` : ""}
                          </option>
                        ))}
                    </select>
                  )}
                </div>
                {bookingError && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p className="text-sm font-medium text-red-800 mb-1">Error</p>
                    <p className="text-xs text-red-700">{bookingError}</p>
                  </div>
                )}
                {emailError && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p className="text-sm font-medium text-red-800 mb-1">Email Error</p>
                    <p className="text-xs text-red-700">{emailError}</p>
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    onClick={handleCreateBooking}
                    disabled={!selectedEventType || selectedCandidates.size === 0 || creatingBooking}
                  >
                    <CalendarIcon className="h-4 w-4 mr-2" />
                    {creatingBooking ? "Creating..." : "Create Booking Link"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleSendEmails}
                    disabled={selectedCandidates.size === 0 || sendingEmails}
                  >
                    <Mail className="h-4 w-4 mr-2" />
                    {sendingEmails ? "Sending..." : "Send Emails"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

