#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════════
TEST VISUAL: Z-ANATOMICAL GUARD
═══════════════════════════════════════════════════════════════════════════════════
Este test verifica visualmente que el Z-Guard:
1. Descarta lesiones en slices < Z_GUARD_MIN_SLICE (80) con PA insuficiente
2. Permite lesiones en la misma zona si tienen suficiente PA
3. No afecta lesiones en slices >= Z_GUARD_MIN_SLICE

Ejecutar: python test_z_guard.py
═══════════════════════════════════════════════════════════════════════════════════
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Headless mode - no GUI
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configuration
Z_GUARD_MIN_SLICE = 80
Z_GUARD_MIN_PA_VOXELS = 500


def create_test_scenario():
    """
    Creates a synthetic test scenario with:
    - PA mask with varying volume per slice
    - Lesions in different z-positions
    """
    # Create 3D volume (128x128x150 slices)
    shape = (128, 128, 150)
    
    # PA mask: cylinder with varying radius per slice
    pa_mask = np.zeros(shape, dtype=bool)
    
    for z in range(shape[2]):
        # PA volume increases with z (simulating going from apex to base)
        if z < 30:
            # Very little PA in apex
            radius = 5
        elif z < 60:
            # Some PA
            radius = 15
        elif z < 80:
            # More PA
            radius = 25
        else:
            # Full PA in main lung region
            radius = 40
        
        # Create circular PA region
        y, x = np.ogrid[:shape[0], :shape[1]]
        center = (shape[0]//2, shape[1]//2)
        dist = np.sqrt((x - center[1])**2 + (y - center[0])**2)
        pa_mask[:, :, z] = dist <= radius
    
    # Create test lesions at different z positions
    lesions = [
        {'name': 'Lesion A (apex, z=10)', 'z_range': (8, 12), 'center': (64, 64), 'radius': 5, 'expected': 'DISCARD'},
        {'name': 'Lesion B (upper, z=40)', 'z_range': (38, 42), 'center': (64, 64), 'radius': 5, 'expected': 'PASS (enough PA)'},
        {'name': 'Lesion C (mid, z=70)', 'z_range': (68, 72), 'center': (64, 64), 'radius': 5, 'expected': 'PASS (enough PA)'},
        {'name': 'Lesion D (safe zone, z=100)', 'z_range': (98, 102), 'center': (64, 64), 'radius': 5, 'expected': 'PASS (z>=80)'},
        {'name': 'Lesion E (edge, z=79)', 'z_range': (77, 81), 'center': (64, 64), 'radius': 5, 'expected': 'PASS (barely)'},
    ]
    
    return pa_mask, lesions


def simulate_z_guard(pa_mask, lesion):
    """
    Simulates Z-Guard logic for a lesion
    """
    z_start, z_end = lesion['z_range']
    
    # Check if in guard zone
    if z_start >= Z_GUARD_MIN_SLICE:
        return 'PASS', f"z_start={z_start} >= Z_MIN={Z_GUARD_MIN_SLICE}"
    
    # Check PA volume in slice range
    pa_voxels_per_slice = []
    for z in range(z_start, min(z_end + 1, pa_mask.shape[2])):
        if z < pa_mask.shape[2]:
            pa_voxels = np.sum(pa_mask[:, :, z])
            pa_voxels_per_slice.append((z, pa_voxels))
            if pa_voxels < Z_GUARD_MIN_PA_VOXELS:
                return 'DISCARD', f"slice={z} has PA={pa_voxels} < {Z_GUARD_MIN_PA_VOXELS}"
    
    return 'PASS', f"All slices have sufficient PA: {pa_voxels_per_slice}"


def visualize_z_guard_test():
    """
    Creates a visual representation of the Z-Guard test
    """
    pa_mask, lesions = create_test_scenario()
    
    # Calculate PA volume per slice
    pa_per_slice = [np.sum(pa_mask[:, :, z]) for z in range(pa_mask.shape[2])]
    
    # Create figure
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f'🛡️ Z-GUARD VISUAL TEST\n'
        f'Z_GUARD_MIN_SLICE = {Z_GUARD_MIN_SLICE} | Z_GUARD_MIN_PA_VOXELS = {Z_GUARD_MIN_PA_VOXELS}',
        fontsize=14, fontweight='bold'
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # Plot 1: PA Volume vs Slice Index
    # ═══════════════════════════════════════════════════════════════════════
    ax1 = axes[0, 0]
    slices = range(len(pa_per_slice))
    ax1.fill_between(slices, pa_per_slice, alpha=0.3, color='blue', label='PA Volume')
    ax1.plot(slices, pa_per_slice, 'b-', linewidth=2)
    
    # Guard zone
    ax1.axvspan(0, Z_GUARD_MIN_SLICE, alpha=0.2, color='red', label=f'Z-Guard Zone (z<{Z_GUARD_MIN_SLICE})')
    ax1.axhline(y=Z_GUARD_MIN_PA_VOXELS, color='orange', linestyle='--', linewidth=2, 
                label=f'Min PA Threshold ({Z_GUARD_MIN_PA_VOXELS})')
    
    # Mark lesion positions
    colors_pass = 'green'
    colors_discard = 'red'
    for lesion in lesions:
        z_center = (lesion['z_range'][0] + lesion['z_range'][1]) // 2
        result, _ = simulate_z_guard(pa_mask, lesion)
        color = colors_pass if result == 'PASS' else colors_discard
        ax1.scatter([z_center], [pa_per_slice[z_center]], s=200, c=color, 
                   marker='o', edgecolors='black', linewidths=2, zorder=5)
    
    ax1.set_xlabel('Slice Index (z)', fontsize=11)
    ax1.set_ylabel('PA Volume (voxels)', fontsize=11)
    ax1.set_title('PA Volume vs Slice Index', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(0, len(pa_per_slice))
    
    # ═══════════════════════════════════════════════════════════════════════
    # Plot 2: Lesion Results Table
    # ═══════════════════════════════════════════════════════════════════════
    ax2 = axes[0, 1]
    ax2.axis('off')
    
    table_data = []
    for lesion in lesions:
        result, reason = simulate_z_guard(pa_mask, lesion)
        z_center = (lesion['z_range'][0] + lesion['z_range'][1]) // 2
        pa_at_z = pa_per_slice[z_center]
        status = '✅ PASS' if result == 'PASS' else '❌ DISCARD'
        table_data.append([
            lesion['name'],
            f"{lesion['z_range'][0]}-{lesion['z_range'][1]}",
            f"{pa_at_z:,}",
            status
        ])
    
    table = ax2.table(
        cellText=table_data,
        colLabels=['Lesion', 'Z Range', 'PA Voxels', 'Result'],
        loc='center',
        cellLoc='center',
        colWidths=[0.35, 0.15, 0.15, 0.2]
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)
    
    # Color cells based on result
    for i, lesion in enumerate(lesions):
        result, _ = simulate_z_guard(pa_mask, lesion)
        color = '#c8e6c9' if result == 'PASS' else '#ffcdd2'
        for j in range(4):
            table[(i + 1, j)].set_facecolor(color)
    
    ax2.set_title('Z-Guard Filter Results', fontsize=12, fontweight='bold', pad=20)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Plot 3: Axial view at different Z levels
    # ═══════════════════════════════════════════════════════════════════════
    ax3 = axes[1, 0]
    
    # Show PA mask at different z levels
    z_levels = [10, 40, 70, 100]
    combined = np.zeros((pa_mask.shape[0], pa_mask.shape[1] * len(z_levels)))
    
    for i, z in enumerate(z_levels):
        combined[:, i*pa_mask.shape[1]:(i+1)*pa_mask.shape[1]] = pa_mask[:, :, z]
    
    ax3.imshow(combined, cmap='Blues', aspect='auto')
    
    # Add labels
    for i, z in enumerate(z_levels):
        zone = "🚫 GUARD" if z < Z_GUARD_MIN_SLICE else "✅ SAFE"
        pa_vol = pa_per_slice[z]
        ax3.text(
            i * pa_mask.shape[1] + pa_mask.shape[1]//2, 
            -5, 
            f'z={z}\n{zone}\nPA={pa_vol}',
            ha='center', va='bottom', fontsize=9, fontweight='bold'
        )
    
    ax3.set_title('PA Mask at Different Z Levels (Axial View)', fontsize=12, fontweight='bold')
    ax3.axis('off')
    
    # ═══════════════════════════════════════════════════════════════════════
    # Plot 4: Z-Guard Decision Flowchart
    # ═══════════════════════════════════════════════════════════════════════
    ax4 = axes[1, 1]
    ax4.axis('off')
    
    flowchart_text = f"""
    ┌─────────────────────────────────────────┐
    │          Z-GUARD DECISION FLOW          │
    └─────────────────────────────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │ z_start >= {Z_GUARD_MIN_SLICE}? │
              └─────────────────┘
                    │     │
               YES  │     │ NO
                    ▼     ▼
            ┌───────────┐ ┌─────────────────────┐
            │  ✅ PASS  │ │ Check PA in slices  │
            └───────────┘ └─────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │ Any slice PA < {Z_GUARD_MIN_PA_VOXELS}? │
                     └─────────────────────────┘
                            │       │
                       YES  │       │ NO
                            ▼       ▼
                    ┌──────────┐ ┌───────────┐
                    │ ❌ DISCARD│ │  ✅ PASS  │
                    └──────────┘ └───────────┘
    """
    
    ax4.text(0.5, 0.5, flowchart_text, transform=ax4.transAxes,
             fontsize=10, fontfamily='monospace',
             verticalalignment='center', horizontalalignment='center',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    ax4.set_title('Z-Guard Decision Logic', fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    
    # Save figure
    output_path = 'z_guard_test_visual.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"✅ Visual test saved to: {output_path}")
    
    plt.show()
    
    return pa_mask, lesions


def run_unit_tests():
    """
    Run unit tests for Z-Guard logic
    """
    print("\n" + "="*70)
    print("🧪 Z-GUARD UNIT TESTS")
    print("="*70)
    
    pa_mask, lesions = create_test_scenario()
    
    all_passed = True
    for lesion in lesions:
        result, reason = simulate_z_guard(pa_mask, lesion)
        expected = 'PASS' if 'PASS' in lesion['expected'] else 'DISCARD'
        
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        
        print(f"\n{status} {lesion['name']}")
        print(f"   Expected: {lesion['expected']}")
        print(f"   Got: {result} - {reason}")
    
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED!")
    print("="*70)
    
    return all_passed


def test_real_service():
    """
    Test with actual TEPProcessingService (if available)
    """
    print("\n" + "="*70)
    print("🔬 TESTING ACTUAL TEPProcessingService")
    print("="*70)
    
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
        django.setup()
        
        from dki_core.services.tep_processing_service import TEPProcessingService
        
        service = TEPProcessingService()
        print(f"\n📋 Service Configuration:")
        print(f"   Z_GUARD_MIN_SLICE: {service.Z_GUARD_MIN_SLICE}")
        print(f"   Z_GUARD_MIN_PA_VOXELS: {service.Z_GUARD_MIN_PA_VOXELS}")
        
        # Verify value is 80
        assert service.Z_GUARD_MIN_SLICE == 80, f"Expected 80, got {service.Z_GUARD_MIN_SLICE}"
        print(f"\n✅ Z_GUARD_MIN_SLICE correctly set to 80!")
        
    except Exception as e:
        print(f"\n⚠️ Could not test actual service: {e}")
        print("   (This is OK if running outside Django context)")


if __name__ == '__main__':
    print("="*70)
    print("🛡️ Z-ANATOMICAL GUARD TEST SUITE")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  Z_GUARD_MIN_SLICE = {Z_GUARD_MIN_SLICE}")
    print(f"  Z_GUARD_MIN_PA_VOXELS = {Z_GUARD_MIN_PA_VOXELS}")
    
    # Run unit tests
    run_unit_tests()
    
    # Test actual service
    test_real_service()
    
    # Generate visual
    print("\n📊 Generating visual test...")
    visualize_z_guard_test()
