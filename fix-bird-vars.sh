#!/bin/bash

# Script to replace all --bird-* variables with --enterprise-* or direct values
# Theme A: Deep Space Gray + Haze Blue

echo "🔧 Replacing Bird theme variables with Enterprise Theme A..."

# Text colors
sed -i '' 's/var(--bird-text-primary)/var(--text-primary)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Text primary fixed"
sed -i '' 's/var(--bird-text-secondary)/var(--text-secondary)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Text secondary fixed"
sed -i '' 's/var(--bird-text-tertiary)/var(--text-tertiary)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Text tertiary fixed"
sed -i '' 's/var(--bird-text-disabled)/var(--text-disabled)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Text disabled fixed"

# Background colors
sed -i '' 's/var(--bird-bg-primary)/var(--bg-primary)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "BG primary fixed"
sed -i '' 's/var(--bird-bg-secondary)/var(--bg-secondary)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "BG secondary fixed"
sed -i '' 's/var(--bird-card-bg)/var(--card-bg)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Card BG fixed"
sed -i '' 's/var(--bird-sidebar-bg)/var(--sidebar-bg)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Sidebar BG fixed"
sed -i '' 's/var(--bird-neutral-50)/var(--gray-50)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Neutral-50 fixed"
sed -i '' 's/var(--bird-neutral-100)/var(--gray-100)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Neutral-100 fixed"
sed -i '' 's/var(--bird-neutral-200)/var(--gray-200)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Neutral-200 fixed"
sed -i '' 's/var(--bird-neutral-300)/var(--gray-300)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Neutral-300 fixed"
sed -i '' 's/var(--bird-neutral-0)/var(--gray-0)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Neutral-0 fixed"

# Primary colors
sed -i '' 's/var(--bird-primary-600)/var(--primary)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Primary fixed"
sed -i '' 's/var(--bird-primary-300)/var(--primary-light)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Primary light fixed"
sed -i '' 's/var(--bird-primary-100)/var(--accent-light)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Accent light fixed"
sed -i '' 's/var(--bird-primary-700)/var(--accent)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Accent fixed"

# Functional colors
sed -i '' 's/var(--bird-success)/var(--success)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Success fixed"
sed -i '' 's/var(--bird-success-bg)/var(--success-bg)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Success BG fixed"
sed -i '' 's/var(--bird-warning)/var(--warning)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Warning fixed"
sed -i '' 's/var(--bird-warning-bg)/var(--warning-bg)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Warning BG fixed"
sed -i '' 's/var(--bird-error)/var(--error)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Error fixed"
sed -i '' 's/var(--bird-error-bg)/var(--error-bg)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Error BG fixed"

# Borders
sed -i '' 's/var(--bird-border)/var(--card-border)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Border fixed"
sed -i '' 's/var(--bird-sidebar-border)/var(--sidebar-border)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Sidebar border fixed"

# Other
sed -i '' 's/var(--bird-shadow-sm)/var(--shadow-sm)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Shadow fixed"
sed -i '' 's/var(--bird-shadow-md)/var(--shadow-md)/g' src/components/**/*.tsx src/pages/**/*.tsx 2>/dev/null || echo "Shadow MD fixed"

echo "✅ Replacement complete!"
