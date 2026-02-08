'use client';

import * as React from 'react';
import {
  X,
  Star,
  Trash2,
  Edit2,
  ChevronDown,
  Save,
  Plus,
  Minus,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/api/auth-context';
import {
  useTagTemplates,
  useCreateTagTemplate,
  useUpdateTagTemplate,
  useDeleteTagTemplate,
  type TagTemplate,
} from '@/hooks/use-tag-templates';
import type { TagFilterSelection } from './TagFilter';

/**
 * Props for the template selector dropdown
 */
export interface TemplateDropdownProps {
  /** Currently selected template ID (if any) */
  selectedTemplateId?: string;
  /** Callback when a template is selected */
  onSelectTemplate: (template: TagTemplate) => void;
  /** Callback to clear template selection */
  onClearTemplate: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Template selector dropdown component
 *
 * Shows a dropdown to select from saved templates.
 * Displays template name, tag counts, and default indicator.
 */
export function TemplateDropdown({
  selectedTemplateId,
  onSelectTemplate,
  onClearTemplate,
  className,
}: TemplateDropdownProps) {
  const { isAuthenticated } = useAuth();
  const { data: templatesData, isLoading } = useTagTemplates({ enabled: isAuthenticated });
  const [isOpen, setIsOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  const templates = templatesData?.items ?? [];
  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId);

  // Close dropdown when clicking outside
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!isAuthenticated) {
    return null;
  }

  if (isLoading) {
    return (
      <div className={cn('h-9 w-40 animate-pulse rounded-lg bg-gray-100', className)} />
    );
  }

  if (templates.length === 0) {
    return null;
  }

  return (
    <div ref={dropdownRef} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors',
          selectedTemplate
            ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
            : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50'
        )}
      >
        {selectedTemplate ? (
          <>
            {selectedTemplate.isDefault && <Star className="h-3.5 w-3.5 fill-current" />}
            <span className="max-w-32 truncate">{selectedTemplate.name}</span>
          </>
        ) : (
          <span>Templates</span>
        )}
        <ChevronDown className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-56 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              onClick={() => {
                onSelectTemplate(template);
                setIsOpen(false);
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
                template.id === selectedTemplateId
                  ? 'bg-indigo-50 text-indigo-700'
                  : 'text-gray-700 hover:bg-gray-50'
              )}
            >
              {template.isDefault ? (
                <Star className="h-3.5 w-3.5 flex-shrink-0 fill-amber-400 text-amber-400" />
              ) : (
                <span className="w-3.5" />
              )}
              <span className="flex-1 truncate">{template.name}</span>
              <span className="flex items-center gap-1 text-xs text-gray-400">
                {template.includeTags.length > 0 && (
                  <span className="flex items-center gap-0.5 text-emerald-600">
                    <Plus className="h-3 w-3" />
                    {template.includeTags.length}
                  </span>
                )}
                {template.excludeTags.length > 0 && (
                  <span className="flex items-center gap-0.5 text-red-600">
                    <Minus className="h-3 w-3" />
                    {template.excludeTags.length}
                  </span>
                )}
              </span>
              {template.id === selectedTemplateId && (
                <Check className="h-4 w-4 text-indigo-600" />
              )}
            </button>
          ))}

          {selectedTemplateId && (
            <>
              <div className="my-1 border-t border-gray-100" />
              <button
                type="button"
                onClick={() => {
                  onClearTemplate();
                  setIsOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-600 hover:bg-gray-50"
              >
                <X className="h-3.5 w-3.5" />
                Clear template
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Props for the save template modal
 */
interface SaveTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  includeTags: string[];
  excludeTags: string[];
  /** Existing template to edit (if editing) */
  editTemplate?: TagTemplate;
  /** Callback after successful save */
  onSaved?: (template: TagTemplate) => void;
}

/**
 * Modal for saving/editing a tag template
 */
export function SaveTemplateModal({
  isOpen,
  onClose,
  includeTags,
  excludeTags,
  editTemplate,
  onSaved,
}: SaveTemplateModalProps) {
  const [name, setName] = React.useState(editTemplate?.name ?? '');
  const [isDefault, setIsDefault] = React.useState(editTemplate?.isDefault ?? false);
  const [error, setError] = React.useState<string | null>(null);

  const createMutation = useCreateTagTemplate();
  const updateMutation = useUpdateTagTemplate();

  const isEditing = !!editTemplate;
  const isPending = createMutation.isPending || updateMutation.isPending;

  // Reset form when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setName(editTemplate?.name ?? '');
      setIsDefault(editTemplate?.isDefault ?? false);
      setError(null);
    }
  }, [isOpen, editTemplate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('Template name is required');
      return;
    }

    setError(null);

    try {
      let savedTemplate: TagTemplate;

      if (isEditing && editTemplate) {
        savedTemplate = await updateMutation.mutateAsync({
          id: editTemplate.id,
          name: trimmedName,
          includeTags,
          excludeTags,
          isDefault,
        });
      } else {
        savedTemplate = await createMutation.mutateAsync({
          name: trimmedName,
          includeTags,
          excludeTags,
          isDefault,
        });
      }

      onSaved?.(savedTemplate);
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to save template');
      }
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-template-title"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" />

      {/* Modal */}
      <div className="relative w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 id="save-template-title" className="text-lg font-semibold text-gray-900">
          {isEditing ? 'Edit Template' : 'Save as Template'}
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Template Name */}
          <div>
            <label htmlFor="template-name" className="block text-sm font-medium text-gray-700">
              Template Name
            </label>
            <input
              id="template-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Sports Only"
              maxLength={255}
              className="mt-1 block w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm placeholder:text-gray-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
              autoFocus
            />
          </div>

          {/* Tag Summary */}
          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-sm font-medium text-gray-700">Tags in this template:</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {includeTags.length === 0 && excludeTags.length === 0 && (
                <span className="text-sm text-gray-400">No tags selected</span>
              )}
              {includeTags.map((tag) => (
                <span
                  key={`include-${tag}`}
                  className="flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700"
                >
                  <Plus className="h-3 w-3" />
                  {tag}
                </span>
              ))}
              {excludeTags.map((tag) => (
                <span
                  key={`exclude-${tag}`}
                  className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700"
                >
                  <Minus className="h-3 w-3" />
                  {tag}
                </span>
              ))}
            </div>
          </div>

          {/* Default Template Toggle */}
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <div>
              <span className="text-sm font-medium text-gray-700">Set as default</span>
              <p className="text-xs text-gray-500">
                Auto-apply this template when opening the page
              </p>
            </div>
          </label>

          {/* Error */}
          {error && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending || !name.trim()}
              className={cn(
                'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors',
                'bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
                (isPending || !name.trim()) && 'cursor-not-allowed opacity-50'
              )}
            >
              {isPending ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Saving...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  {isEditing ? 'Update' : 'Save'}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * Props for the template manager component
 */
export interface TagTemplateManagerProps {
  /** Current filter selection (for Save Template) */
  currentSelection: TagFilterSelection;
  /** Callback when a template is applied */
  onApplyTemplate: (selection: TagFilterSelection) => void;
  /** Optional callback when selection is cleared */
  onClearSelection?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Tag Template Manager component
 *
 * Sprint 07 - Event Tags: Frontend Tag Templates UI
 *
 * Features:
 * - Template selector dropdown to quickly apply saved templates
 * - Save as Template button (opens modal)
 * - Edit and delete functionality for each template
 * - Default template indicator (star icon)
 * - Auto-apply default template on mount
 */
export function TagTemplateManager({
  currentSelection,
  onApplyTemplate,
  onClearSelection,
  className,
}: TagTemplateManagerProps) {
  const { isAuthenticated } = useAuth();
  const { data: templatesData, isLoading } = useTagTemplates({ enabled: isAuthenticated });
  const deleteMutation = useDeleteTagTemplate();

  const [selectedTemplateId, setSelectedTemplateId] = React.useState<string | undefined>();
  const [saveModalOpen, setSaveModalOpen] = React.useState(false);
  const [editingTemplate, setEditingTemplate] = React.useState<TagTemplate | undefined>();
  const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(null);

  const templates = templatesData?.items ?? [];
  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId);

  // Auto-apply default template on mount
  const defaultAppliedRef = React.useRef(false);
  React.useEffect(() => {
    if (defaultAppliedRef.current || isLoading || !templatesData) return;

    const defaultTemplate = templates.find((t) => t.isDefault);
    if (defaultTemplate) {
      onApplyTemplate({
        includeTags: defaultTemplate.includeTags,
        excludeTags: defaultTemplate.excludeTags,
      });
      setSelectedTemplateId(defaultTemplate.id);
    }
    defaultAppliedRef.current = true;
  }, [isLoading, templatesData, templates, onApplyTemplate]);

  const handleSelectTemplate = (template: TagTemplate) => {
    setSelectedTemplateId(template.id);
    onApplyTemplate({
      includeTags: template.includeTags,
      excludeTags: template.excludeTags,
    });
  };

  const handleClearTemplate = () => {
    setSelectedTemplateId(undefined);
    onClearSelection?.();
  };

  const handleEditTemplate = (template: TagTemplate) => {
    setEditingTemplate(template);
    setSaveModalOpen(true);
  };

  const handleDeleteTemplate = async (templateId: string) => {
    try {
      await deleteMutation.mutateAsync(templateId);
      if (selectedTemplateId === templateId) {
        setSelectedTemplateId(undefined);
      }
      setConfirmDeleteId(null);
    } catch (err) {
      console.error('Failed to delete template:', err);
    }
  };

  const handleSaveComplete = (template: TagTemplate) => {
    setSelectedTemplateId(template.id);
    setEditingTemplate(undefined);
  };

  const handleOpenSaveModal = () => {
    setEditingTemplate(undefined);
    setSaveModalOpen(true);
  };

  const handleCloseSaveModal = () => {
    setSaveModalOpen(false);
    setEditingTemplate(undefined);
  };

  const hasSelection =
    currentSelection.includeTags.length > 0 || currentSelection.excludeTags.length > 0;

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      {/* Template Dropdown */}
      <TemplateDropdown
        selectedTemplateId={selectedTemplateId}
        onSelectTemplate={handleSelectTemplate}
        onClearTemplate={handleClearTemplate}
      />

      {/* Selected Template Actions */}
      {selectedTemplate && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => handleEditTemplate(selectedTemplate)}
            className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            title="Edit template"
          >
            <Edit2 className="h-4 w-4" />
          </button>
          {confirmDeleteId === selectedTemplate.id ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => handleDeleteTemplate(selectedTemplate.id)}
                disabled={deleteMutation.isPending}
                className="rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-200"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Confirm'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDeleteId(null)}
                className="rounded-md px-2 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDeleteId(selectedTemplate.id)}
              className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600"
              title="Delete template"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {/* Save as Template Button */}
      {hasSelection && !selectedTemplate && (
        <button
          type="button"
          onClick={handleOpenSaveModal}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50"
        >
          <Save className="h-4 w-4" />
          Save Template
        </button>
      )}

      {/* Save Template Modal */}
      <SaveTemplateModal
        isOpen={saveModalOpen}
        onClose={handleCloseSaveModal}
        includeTags={editingTemplate?.includeTags ?? currentSelection.includeTags}
        excludeTags={editingTemplate?.excludeTags ?? currentSelection.excludeTags}
        editTemplate={editingTemplate}
        onSaved={handleSaveComplete}
      />
    </div>
  );
}

export default TagTemplateManager;
