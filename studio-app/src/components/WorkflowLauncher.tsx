import { useState, useEffect } from 'react'
import { Play, Clock, Package, MessageSquare, ChevronRight, Loader2, CheckCircle, XCircle, AlertCircle } from 'lucide-react'

// Types for workflow data
interface WorkflowDefinition {
  workflow_id: string
  title: string
  description: string
  version: string
  category: string
  steps: Array<{
    step_id: string
    name: string
    description: string
    step_type: string
    required_inputs: string[]
    optional_inputs: string[]
    depends_on: string[]
    timeout_seconds: number
    retry_count: number
  }>
  required_inputs: Record<string, any>
  optional_inputs: Record<string, any>
  estimated_duration_minutes: number
  status: string
  tags: string[]
}

interface WorkflowExecution {
  execution_id: string
  workflow_id: string
  project_id: string
  status: string
  started_at?: string
  completed_at?: string
  current_step?: string
  completed_steps: string[]
  failed_steps: string[]
  step_results: Record<string, any>
  inputs: Record<string, any>
  outputs: Record<string, any>
  error_message?: string
  progress_percentage: number
}

interface WorkflowLauncherProps {
  projectId: string
  onWorkflowComplete?: (execution: WorkflowExecution) => void
}

export default function WorkflowLauncher({ projectId, onWorkflowComplete }: WorkflowLauncherProps) {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([])
  const [executions, setExecutions] = useState<WorkflowExecution[]>([])
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDefinition | null>(null)
  const [isExecuting, setIsExecuting] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [error, setError] = useState<string | null>(null)

  // Load available workflows
  useEffect(() => {
    loadWorkflows()
    loadExecutions()
  }, [])

  const loadWorkflows = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/workflows/definitions`)
      const data = await response.json()
      setWorkflows(data)
    } catch (err) {
      console.error('Failed to load workflows:', err)
    }
  }

  const loadExecutions = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/workflows/executions?project_id=${projectId}`)
      const data = await response.json()
      setExecutions(data)
    } catch (err) {
      console.error('Failed to load executions:', err)
    }
  }

  const handleWorkflowSelect = (workflow: WorkflowDefinition) => {
    setSelectedWorkflow(workflow)
    setShowForm(true)
    setFormData({})
    setError(null)
  }

  const handleInputChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }))
  }

  const handleExecute = async () => {
    if (!selectedWorkflow) return

    // Validate required inputs
    const missingInputs = Object.keys(selectedWorkflow.required_inputs).filter(
      key => !formData[key] || formData[key].trim() === ''
    )
    
    if (missingInputs.length > 0) {
      setError(`Missing required inputs: ${missingInputs.join(', ')}`)
      return
    }

    setIsExecuting(true)
    setError(null)

    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/workflows/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          workflow_id: selectedWorkflow.workflow_id,
          project_id: projectId,
          inputs: formData,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Execution failed')
      }

      const execution = await response.json()
      
      // Update executions list
      setExecutions(prev => [execution, ...prev])
      
      // Poll for completion
      pollExecution(execution.execution_id)
      
      setShowForm(false)
      setSelectedWorkflow(null)
      setFormData({})
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Execution failed')
      setIsExecuting(false)
    }
  }

  const pollExecution = async (executionId: string) => {
    const poll = async () => {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/workflows/executions/${executionId}`)
        const execution = await response.json()
        
        setExecutions(prev => prev.map(e => e.execution_id === executionId ? execution : e))
        
        if (execution.status === 'completed') {
          setIsExecuting(false)
          onWorkflowComplete?.(execution)
        } else if (execution.status === 'failed') {
          setIsExecuting(false)
          setError(execution.error_message || 'Workflow failed')
        } else if (execution.status === 'running') {
          // Continue polling
          setTimeout(poll, 2000)
        }
      } catch (err) {
        console.error('Failed to poll execution:', err)
        setIsExecuting(false)
      }
    }

    setTimeout(poll, 2000)
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-500" />
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />
      case 'running':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
      case 'cancelled':
        return <AlertCircle className="w-4 h-4 text-yellow-500" />
      default:
        return <Clock className="w-4 h-4 text-gray-500" />
    }
  }

  const getWorkflowIcon = (category: string) => {
    switch (category) {
      case 'quick_film':
        return <Play className="w-5 h-5" />
      case 'revision':
        return <MessageSquare className="w-5 h-5" />
      case 'package':
        return <Package className="w-5 h-5" />
      case 'review':
        return <MessageSquare className="w-5 h-5" />
      default:
        return <Play className="w-5 h-5" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Available Workflows */}
      <div className="studio-surface p-6">
        <h3 className="text-lg font-semibold text-zinc-100 mb-4">Available Workflows</h3>
        <div className="grid gap-4">
          {workflows.map(workflow => (
            <div
              key={workflow.workflow_id}
              className="flex items-center justify-between p-4 bg-zinc-800/50 rounded-lg border border-zinc-700/50 hover:border-zinc-600/50 transition-colors cursor-pointer"
              onClick={() => handleWorkflowSelect(workflow)}
            >
              <div className="flex items-center space-x-4">
                <div className="p-2 bg-amber-500/20 rounded-lg">
                  {getWorkflowIcon(workflow.category)}
                </div>
                <div>
                  <h4 className="text-zinc-100 font-medium">{workflow.title}</h4>
                  <p className="text-zinc-400 text-sm">{workflow.description}</p>
                  <div className="flex items-center space-x-4 mt-1 text-xs text-zinc-500">
                    <span>{workflow.estimated_duration_minutes} min</span>
                    <span>•</span>
                    <span>{workflow.steps.length} steps</span>
                    <span>•</span>
                    <span>{workflow.version}</span>
                  </div>
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-zinc-400" />
            </div>
          ))}
        </div>
      </div>

      {/* Recent Executions */}
      {executions.length > 0 && (
        <div className="studio-surface p-6">
          <h3 className="text-lg font-semibold text-zinc-100 mb-4">Recent Executions</h3>
          <div className="space-y-3">
            {executions.slice(0, 5).map(execution => {
              const workflow = workflows.find(w => w.workflow_id === execution.workflow_id)
              return (
                <div
                  key={execution.execution_id}
                  className="flex items-center justify-between p-3 bg-zinc-800/30 rounded-lg"
                >
                  <div className="flex items-center space-x-3">
                    {getStatusIcon(execution.status)}
                    <div>
                      <div className="text-zinc-100 font-medium">
                        {workflow?.title || execution.workflow_id}
                      </div>
                      <div className="text-zinc-400 text-sm">
                        {execution.started_at && new Date(execution.started_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-zinc-400 text-sm capitalize">{execution.status}</div>
                    {execution.progress_percentage > 0 && (
                      <div className="text-zinc-500 text-xs">{Math.round(execution.progress_percentage)}%</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Workflow Execution Form */}
      {showForm && selectedWorkflow && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="studio-surface p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-zinc-100 mb-4">
              Execute: {selectedWorkflow.title}
            </h3>
            
            {/* Required Inputs */}
            <div className="space-y-4 mb-6">
              {Object.entries(selectedWorkflow.required_inputs).map(([key, description]) => (
                <div key={key}>
                  <label className="block text-zinc-300 text-sm font-medium mb-1">
                    {key} <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={formData[key] || ''}
                    onChange={(e) => handleInputChange(key, e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700/50 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50"
                    placeholder={description}
                  />
                </div>
              ))}
              
              {/* Optional Inputs */}
              {Object.entries(selectedWorkflow.optional_inputs).map(([key, description]) => (
                <div key={key}>
                  <label className="block text-zinc-300 text-sm font-medium mb-1">
                    {key}
                  </label>
                  <input
                    type="text"
                    value={formData[key] || ''}
                    onChange={(e) => handleInputChange(key, e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700/50 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50"
                    placeholder={description}
                  />
                </div>
              ))}
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
                {error}
              </div>
            )}

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowForm(false)}
                disabled={isExecuting}
                className="px-4 py-2 bg-zinc-700/50 text-zinc-300 rounded-lg hover:bg-zinc-700/70 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleExecute}
                disabled={isExecuting}
                className="px-4 py-2 bg-amber-500/20 text-amber-400 rounded-lg hover:bg-amber-500/30 transition-colors disabled:opacity-50 flex items-center space-x-2"
              >
                {isExecuting && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{isExecuting ? 'Executing...' : 'Execute'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
