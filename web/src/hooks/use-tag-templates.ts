/**
 * React Query hooks for tag templates functionality
 *
 * Sprint 07 - Event Tags: Frontend Tag Templates UI
 *
 * Provides:
 * - useTagTemplates() - Fetch user's tag templates
 * - useCreateTagTemplate() - Create a new template
 * - useUpdateTagTemplate() - Update an existing template
 * - useDeleteTagTemplate() - Delete a template
 *
 * Features:
 * - Optimistic updates for instant UI feedback
 * - Automatic cache invalidation
 * - Error rollback on mutation failure
 * - Calls FastAPI backend /api/v1/tag-templates endpoints
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest, ApiError, getAccessToken } from '@/lib/api/client';

/**
 * Tag template data returned by the API
 */
export interface TagTemplate {
  id: string;
  name: string;
  includeTags: string[];
  excludeTags: string[];
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
}

/**
 * Response type for GET /api/v1/tag-templates
 */
export interface TagTemplatesResponse {
  items: TagTemplate[];
  count: number;
}

/**
 * Request type for creating a tag template
 */
export interface CreateTagTemplateRequest {
  name: string;
  includeTags: string[];
  excludeTags: string[];
  isDefault?: boolean;
}

/**
 * Request type for updating a tag template
 */
export interface UpdateTagTemplateRequest {
  name?: string;
  includeTags?: string[];
  excludeTags?: string[];
  isDefault?: boolean;
}

/**
 * Fetch user's tag templates from the API
 */
async function fetchTagTemplates(): Promise<TagTemplatesResponse> {
  // Return empty list if not authenticated
  if (!getAccessToken()) {
    return { items: [], count: 0 };
  }

  try {
    return await apiRequest<TagTemplatesResponse>('/tag-templates');
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return { items: [], count: 0 };
    }
    throw error;
  }
}

/**
 * Create a new tag template
 */
async function createTagTemplate(data: CreateTagTemplateRequest): Promise<TagTemplate> {
  return apiRequest<TagTemplate>('/tag-templates', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Update an existing tag template
 */
async function updateTagTemplate({
  id,
  ...data
}: UpdateTagTemplateRequest & { id: string }): Promise<TagTemplate> {
  return apiRequest<TagTemplate>(`/tag-templates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Delete a tag template
 */
async function deleteTagTemplate(id: string): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    throw new ApiError('Not authenticated', 401, 'Please log in');
  }

  const response = await fetch(`/api/v1/tag-templates/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError('Template not found', 404, 'Template not found');
    }
    const error = await response.json().catch(() => ({}));
    throw new ApiError(error.detail || 'Failed to delete template', response.status, error.detail);
  }
}

/**
 * Hook to fetch user's tag templates
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useTagTemplates();
 *
 * // Get the default template
 * const defaultTemplate = data?.items.find(t => t.isDefault);
 *
 * // List all templates
 * data?.items.forEach(template => {
 *   console.log(template.name, template.includeTags);
 * });
 * ```
 */
export function useTagTemplates(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;
  const hasToken = typeof window !== 'undefined' && !!getAccessToken();

  return useQuery({
    queryKey: ['tag-templates'],
    queryFn: fetchTagTemplates,
    enabled: enabled && hasToken,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to create a new tag template with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: create, isPending } = useCreateTagTemplate();
 *
 * create({
 *   name: 'Sports Only',
 *   includeTags: ['Sports', 'Basketball'],
 *   excludeTags: ['Politics'],
 *   isDefault: true,
 * }, {
 *   onSuccess: (template) => console.log('Created:', template.id),
 *   onError: (error) => console.error(error),
 * });
 * ```
 */
export function useCreateTagTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createTagTemplate,
    onMutate: async (newTemplate) => {
      await queryClient.cancelQueries({ queryKey: ['tag-templates'] });
      const previousData = queryClient.getQueryData<TagTemplatesResponse>(['tag-templates']);

      if (previousData) {
        const optimisticTemplate: TagTemplate = {
          id: `temp-${Date.now()}`,
          name: newTemplate.name,
          includeTags: newTemplate.includeTags,
          excludeTags: newTemplate.excludeTags,
          isDefault: newTemplate.isDefault ?? false,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

        // If setting as default, unset previous default
        const updatedItems = newTemplate.isDefault
          ? previousData.items.map((t) => ({ ...t, isDefault: false }))
          : previousData.items;

        queryClient.setQueryData<TagTemplatesResponse>(['tag-templates'], {
          items: [...updatedItems, optimisticTemplate],
          count: previousData.count + 1,
        });
      }

      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['tag-templates'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tag-templates'] });
    },
  });
}

/**
 * Hook to update an existing tag template with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: update, isPending } = useUpdateTagTemplate();
 *
 * update({
 *   id: templateId,
 *   name: 'Updated Name',
 *   isDefault: true,
 * }, {
 *   onSuccess: (template) => console.log('Updated:', template.name),
 *   onError: (error) => console.error(error),
 * });
 * ```
 */
export function useUpdateTagTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateTagTemplate,
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: ['tag-templates'] });
      const previousData = queryClient.getQueryData<TagTemplatesResponse>(['tag-templates']);

      if (previousData) {
        const updatedItems = previousData.items.map((template) => {
          if (template.id === variables.id) {
            return {
              ...template,
              ...variables,
              updatedAt: new Date().toISOString(),
            };
          }
          // If setting new default, unset others
          if (variables.isDefault && template.isDefault) {
            return { ...template, isDefault: false };
          }
          return template;
        });

        queryClient.setQueryData<TagTemplatesResponse>(['tag-templates'], {
          ...previousData,
          items: updatedItems,
        });
      }

      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['tag-templates'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tag-templates'] });
    },
  });
}

/**
 * Hook to delete a tag template with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: deleteTemplate, isPending } = useDeleteTagTemplate();
 *
 * deleteTemplate(templateId, {
 *   onSuccess: () => console.log('Deleted!'),
 *   onError: (error) => console.error(error),
 * });
 * ```
 */
export function useDeleteTagTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteTagTemplate,
    onMutate: async (templateId) => {
      await queryClient.cancelQueries({ queryKey: ['tag-templates'] });
      const previousData = queryClient.getQueryData<TagTemplatesResponse>(['tag-templates']);

      if (previousData) {
        queryClient.setQueryData<TagTemplatesResponse>(['tag-templates'], {
          items: previousData.items.filter((t) => t.id !== templateId),
          count: previousData.count - 1,
        });
      }

      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['tag-templates'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tag-templates'] });
    },
  });
}
