
set PYTHONPATH=C:\Python27\Lib\site-packages;C:\Python27;C:\Python27\Lib
set PATH=C:\Python27;C:\Python27\Scripts;C:\Windows;C:\Windows\System32
set POPGEN_PATH=Q:\Model Programs\PopGen_1_1_2013\popgen

mkdir outputs

echo %DATE% %TIME% >> popgen_run.log
python "%POPGEN_PATH%\popgen_run.py" sfcta_config.xml 0 >> popgen_run.log 2>&1
echo %DATE% %TIME% >> popgen_run.log

:: if it doesn't exist, try to export it
IF NOT EXIST outputs\person_synthetic_data.dat (
  echo %DATE% %TIME% >> popgen_export.log
  python "%POPGEN_PATH%\popgen_run.py" -e sfcta_config.xml 0 >> popgen_export.log 2>&1
  echo %DATE% %TIME% >> popgen_export.log
)

:: if it still doesn't exist then fail
IF NOT EXIST outputs\person_synthetic_data.dat goto done


cd outputs
:: ==================================================================================
:: Sumarize the *original* synthesized population - need to use 64bit python
::
set PYTHONPATH=C:\Python27-64bit\Lib\site-packages;C:\Python27-64bit;C:\Python27-64bit\Lib
set PATH=C:\Python27-64bit;C:\Python27-64bit\Scripts;C:\Windows;C:\Windows\System32
set PYTHONLIB=Q:\Model Development\Population Synthesizer\pythonlib

:orig
:: j/k don't bother
goto new

set ORIG_SFSAMP=Y:\champ\landuse\p2011\SCS.JobsHousingConnection.Spring2013update\2010\PopSyn9County\outputs\syntheticPop\sfsamp.txt
set ORIG_TAZDATA_CONVERTED=Y:\champ\landuse\p2011\SCS.JobsHousingConnection.Spring2013update\2010\PopSyn9County\inputs\converted\tazdata_converted.csv

:: convert the original sfsamp.txt to one sorted by taz,hhid,persid
python "%PYTHONLIB%\sort_sfsamp_by_taz_hhid_persid.py" %ORIG_SFSAMP% sfsamp_orig_sorted.txt

:: summarize it
python "%PYTHONLIB%\summarize_sfsamp.py" sfsamp_orig_sorted.txt %ORIG_TAZDATA_CONVERTED% sfsamp_orig_summary.xlsx

:: ==================================================================================
:: Summarize the *new* synthesized population

:new
:: convert the PopGen result to sfsamp.txt
::   Inputs: person_synthetic_data.dat, person_synthetic_data_meta.txt
::   Outputs: person_synthetic_data_hhldstogether.dat 
python "%PYTHONLIB%\reorder_freq_hhlds_together.py"

::   Inputs: person_synthetic_data_hhldstogether.dat
::   Outputs: sfsamp.txt
python "%PYTHONLIB%\reformat_person_synthetic_data_to_sfsamp.py"

:: summarize it
python "%PYTHONLIB%\summarize_sfsamp.py" sfsamp.txt %ORIG_TAZDATA_CONVERTED% sfsamp_summary.xlsx

:done