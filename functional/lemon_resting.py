# -*- coding: utf-8 -*-
"""
Created on Mon Feb  9 12:26:20 2015

@author: fbeyer
"""

from nipype.pipeline.engine import Node, Workflow
import nipype.interfaces.utility as util
import nipype.interfaces.io as nio
import nipype.interfaces.fsl as fsl
from ants_registration import create_ants_registration_pipeline
from denoise import create_denoise_pipeline
from smoothing import create_smoothing_pipeline
from visualize import create_visualize_pipeline
from slicetiming_correction import create_slice_timing_pipeline

'''
Main workflow for lemon resting state preprocessing.
====================================================
Uses file structure set up by conversion script.
'''
def create_lemon_resting(subject, working_dir, data_dir, data_dir_WDR, freesurfer_dir, out_dir,
    vol_to_remove, TR, epi_resolution, highpass, lowpass,
    echo_space, te_diff, pe_dir, standard_brain, standard_brain_resampled, standard_brain_mask, 
    standard_brain_mask_resampled, fwhm_smoothing):
    # set fsl output type to nii.gz
    fsl.FSLCommand.set_default_output_type('NIFTI_GZ')
    # main workflow
    func_preproc = Workflow(name='lemon_resting')
    func_preproc.base_dir = working_dir
    func_preproc.config['execution']['crashdump_dir'] = func_preproc.base_dir + "/crash_files"
    # select files
   
   
       # select files
    templates={
    'anat_brain' : 'preprocessed/mod/anat/brain.nii.gz', 
    'brain_mask' : 'preprocessed/mod/anat/T1_brain_mask.nii.gz',
    'ants_affine': 'preprocessed/mod/anat/transforms2mni/transform0GenericAffine.mat',
    'ants_warp':   'preprocessed/mod/anat/transforms2mni/transform1Warp.nii.gz',

    }
         
    templates_WDR={
    'par_moco': 'lemon_resting/motion_correction/mcflirt/rest_realigned.nii.gz.par',
    'trans_ts': 'lemon_resting/transform_timeseries/merge/rest2anat.nii.gz',
    'epi2anat_dat': 'lemon_resting/fmap_coreg/bbregister/rest2anat.dat',
    'unwarped_mean_epi2fmap': 'lemon_resting/fmap_coreg/applywarp0/rest_mean2fmap_unwarped.nii.gz',
     
    }
    
    selectfiles = Node(nio.SelectFiles(templates, base_directory=data_dir),    name="selectfiles")
    selectfiles_WDR = Node(nio.SelectFiles(templates_WDR, base_directory=data_dir_WDR),    name="selectfiles_WDR")
   
      
       
          
    # workflow to denoise timeseries
    denoise = create_denoise_pipeline()
    denoise.inputs.inputnode.highpass_sigma= 1./(2*TR*highpass)
    denoise.inputs.inputnode.lowpass_sigma= 1./(2*TR*lowpass)
    #https://www.jiscmail.ac.uk/cgi-bin/webadmin?A2=ind1205&L=FSL&P=R57592&1=FSL&9=A&I=-3&J=on&d=No+Match%3BMatch%3BMatches&z=4
    denoise.inputs.inputnode.tr = TR
    
    #workflow to transform timeseries to MNI
    ants_registration=create_ants_registration_pipeline()
    ants_registration.inputs.inputnode.ref=standard_brain_resampled    
    
    #workflow to smooth
    smoothing = create_smoothing_pipeline() 
    smoothing.inputs.inputnode.fwhm=fwhm_smoothing
   
    #workflow to slice time in the end as a try
    slicetiming = create_slice_timing_pipeline() 
    
    #visualize registration results
    visualize = create_visualize_pipeline()
    visualize.inputs.inputnode.mni_template=standard_brain_resampled 
    

    
    #sink to store files
    sink = Node(nio.DataSink(parameterization=False,
    base_directory=out_dir,
    substitutions=[('fmap_phase_fslprepared', 'fieldmap'),
    ('fieldmap_fslprepared_fieldmap_unmasked_vsm', 'shiftmap'),
    ('plot.rest_coregistered', 'outlier_plot'),
    ('filter_motion_comp_norm_compcor_art_dmotion', 'nuissance_matrix'),
    ('rest_realigned.nii.gz_abs.rms', 'rest_realigned_abs.rms'),
    ('rest_realigned.nii.gz.par','rest_realigned.par'),
    ('rest_realigned.nii.gz_rel.rms', 'rest_realigned_rel.rms'),
    ('rest_realigned.nii.gz_abs_disp', 'abs_displacement_plot'),
    ('rest_realigned.nii.gz_rel_disp', 'rel_displacment_plot'),
    ('art.rest_coregistered_outliers', 'outliers'),
    ('global_intensity.rest_coregistered', 'global_intensity'),
    ('norm.rest_coregistered', 'composite_norm'),
    ('stats.rest_coregistered', 'stats'),
    ('rest_denoised_bandpassed_norm.nii.gz', 'rest_preprocessed_nativespace.nii.gz'),
    ('rest_denoised_bandpassed_norm_trans.nii.gz', 'rest_mni_unsmoothed.nii.gz'),
    ('rest_denoised_bandpassed_norm_trans_smooth.nii', 'rest_mni_smoothed.nii')]),
    name='sink')
    
    
    # connections
    func_preproc.connect([
    
    #correct slicetiming
    (selectfiles_WDR, slicetiming, [('trans_ts', 'inputnode.ts')]),
    (slicetiming, denoise, [('outputnode.ts_slicetcorrected','inputnode.epi_coreg')]),
    
    #denoise data
    (selectfiles, denoise, [('brain_mask', 'inputnode.brain_mask'),
    ('anat_brain', 'inputnode.anat_brain')]),
    (selectfiles_WDR, denoise, [('par_moco', 'inputnode.moco_par')]),
    (selectfiles_WDR, denoise, [('epi2anat_dat', 'inputnode.epi2anat_dat'),
    ('unwarped_mean_epi2fmap', 'inputnode.unwarped_mean')]),
    (denoise, ants_registration, [('outputnode.normalized_file', 'inputnode.denoised_ts')]),
        
   
    #registration to MNI space
    (selectfiles, ants_registration, [('ants_affine', 'inputnode.ants_affine')] ),
    (selectfiles, ants_registration, [('ants_warp', 'inputnode.ants_warp')] ),

    (ants_registration, smoothing, [('outputnode.ants_reg_ts', 'inputnode.ts_transformed')]),

    (smoothing, visualize,  [('outputnode.ts_smoothed', 'inputnode.ts_transformed')]),


    ##all the output
    (denoise, sink, [
    ('outputnode.wmcsf_mask', 'denoise.mask.@wmcsf_masks'),
    ('outputnode.combined_motion','denoise.artefact.@combined_motion'),
    ('outputnode.outlier_files','denoise.artefact.@outlier'),
    ('outputnode.intensity_files','denoise.artefact.@intensity'),
    ('outputnode.outlier_stats','denoise.artefact.@outlierstats'),
    ('outputnode.outlier_plots','denoise.artefact.@outlierplots'),
    ('outputnode.mc_regressor', 'denoise.regress.@mc_regressor'),
    ('outputnode.comp_regressor', 'denoise.regress.@comp_regressor'),
    ('outputnode.mc_F', 'denoise.regress.@mc_F'),
    ('outputnode.mc_pF', 'denoise.regress.@mc_pF'),
    ('outputnode.comp_F', 'denoise.regress.@comp_F'),
    ('outputnode.comp_pF', 'denoise.regress.@comp_pF'),
    ('outputnode.brain_mask_resamp', 'denoise.mask.@brain_resamp'),
    ('outputnode.brain_mask2epi', 'denoise.mask.@brain_mask2epi'),
    ('outputnode.normalized_file', 'denoise.@normalized')
    ]),
    (ants_registration, sink, [('outputnode.ants_reg_ts', 'ants.@antsnormalized')
    ]),
    (smoothing, sink, [('outputnode.ts_smoothed', '@smoothed.FWHM6')]),
    ])

    #func_preproc.write_graph(dotfilename='func_preproc.dot', graph2use='colored', format='pdf', simple_form=True)
    func_preproc.run()
    # plugin='MultiProc'plugin='MultiProc'plugin='CondorDAGMan')
    #func_preproc.run()plugin='CondorDAGMan'plugin='CondorDAGMan'plugin='CondorDAGMan'plugin='CondorDAGMan'
#plugin='CondorDAGMan'