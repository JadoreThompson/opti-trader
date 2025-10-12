import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

/**
 * Returns a titled version of the passed string.
 * @param value
 * @returns {string}
 */
export function formatUnderscore(value: string): string {
    const parts = value.toLowerCase().split('_')
    return parts.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(' ')
}
